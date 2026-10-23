"""The gateway against real Postgres and Valkey, with a fake sandbox driver (no Docker).

Security gate (PLAN phase 4): tickets are single-use, expire, and are bound to one attempt
and one channel; foreign origins are refused; /internal needs a signature over method, path
and body; the file API refuses paths that leave the repo.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from conftest import valkey_url_for_tests
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from devgrill.config import Settings
from devgrill.domain.enums import AttemptMode, AttemptState
from devgrill.infra.models import Attempt, AttemptEvent, Recording
from devgrill.infra.signing import Ticket, issue_ticket, signed_headers
from devgrill.sandbox.compose import safe_repo_path
from devgrill.sandbox.driver import DeployResult, LogLine
from devgrill_content.seed import seed
from devgrill_gateway.control import dispatch
from devgrill_gateway.main import create_app

pytestmark = pytest.mark.integration

CONTENT = Path(__file__).resolve().parents[3] / "content"
SECRET = "g" * 40
ORIGIN = "http://localhost:3000"


class FakePty:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.sizes: list[tuple[int, int]] = []
        self.closed = False

    async def read(self) -> bytes | None:
        return await self.queue.get()

    async def write(self, data: bytes) -> None:
        await self.queue.put(b"echo:" + data)  # the "shell" echoes what it gets

    async def resize(self, cols: int, rows: int) -> None:
        self.sizes.append((cols, rows))

    async def close(self) -> None:
        self.closed = True
        await self.queue.put(None)


class FakeDriver:
    def __init__(self) -> None:
        self.ptys: list[FakePty] = []
        self.restarted: list[str] = []
        self.files = {"app/main.py": b"print('hi')\n"}

    async def exec_pty(self, handle: Any, service: str, argv: list[str], **kw: Any) -> FakePty:
        assert argv[0] == "tmux"
        pty = FakePty()
        await pty.resize(kw["cols"], kw["rows"])
        self.ptys.append(pty)
        return pty

    async def attach_probe(self, handle: Any, argv: list[str]) -> FakePty:
        return FakePty()

    async def status(self, handle: Any) -> list[dict[str, Any]]:
        return [
            {
                "name": "api",
                "state": "running",
                "health": "healthy",
                "restarts": 0,
                "oom_killed": False,
                "started_at": None,
            }
        ]

    async def restart(self, handle: Any, service: str) -> None:
        self.restarted.append(service)

    async def list_files(self, handle: Any, bundle: Any, service: str) -> list[str]:
        return sorted(self.files)

    async def read_file(self, handle: Any, bundle: Any, service: str, path: str) -> bytes:
        rel = safe_repo_path(path)
        if rel not in self.files:
            raise FileNotFoundError(rel)
        return self.files[rel]

    async def write_file(
        self, handle: Any, bundle: Any, service: str, path: str, data: bytes
    ) -> None:
        self.files[safe_repo_path(path)] = data

    async def deploy(
        self, handle: Any, bundle: Any, service: str, ref: str | None = None
    ) -> DeployResult:
        return DeployResult(True, ref or "abc1234", f"{service} is live", "")

    async def exec(self, handle: Any, service: str, argv: list[str], **kw: Any) -> Any:
        class R:
            stdout = ""
            ok = True

        return R()

    async def follow_logs(self, handle: Any, **kw: Any) -> AsyncIterator[LogLine]:
        from datetime import UTC, datetime

        yield LogLine(datetime.now(UTC), "api", '{"msg": "slow or failed request"}')
        await asyncio.sleep(3600)

    async def close(self) -> None:
        pass


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data


@pytest.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    await seed(db_session, CONTENT)
    await db_session.commit()
    return db_session


@pytest.fixture
def gateway(
    migrated_database: str, db_engine: object
) -> Iterator[tuple[TestClient, FakeDriver, FakeStore]]:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        log_format="json",
        database_url=migrated_database,
        valkey_url=valkey_url_for_tests(),
        internal_hmac_secret=SECRET,
        gateway_ws_origins=ORIGIN,
        content_root=CONTENT,
    )
    app = create_app(settings)
    driver, store = FakeDriver(), FakeStore()
    app.state.driver = driver
    app.state.store = store
    with TestClient(app) as client:
        assert client.portal is not None
        client.portal.call(app.state.valkey.flushdb)
        yield client, driver, store


async def make_attempt(
    session: AsyncSession, state: AttemptState = AttemptState.ACTIVE
) -> uuid.UUID:
    version = await session.scalar(
        text("SELECT current_version_id FROM app.scenarios WHERE slug = 'ttl-zero'")
    )
    attempt = Attempt(
        guest_token_hash=f"g-{uuid.uuid4().hex}",
        scenario_version_id=version,
        mode=AttemptMode.GUIDED,
        state=state,
    )
    session.add(attempt)
    await session.commit()
    return attempt.id


def ticket_for(
    client: TestClient, attempt_id: uuid.UUID, kind: str = "terminal", ttl: int = 60
) -> str:
    assert client.portal is not None
    valkey = client.app.state.valkey  # type: ignore[attr-defined]
    return client.portal.call(issue_ticket, valkey, Ticket(str(attempt_id), kind, "guest:x"), ttl)  # type: ignore[arg-type]


def close_code(client: TestClient, url: str, origin: str | None = ORIGIN) -> int:
    headers = {"origin": origin} if origin else {}
    with (
        pytest.raises(WebSocketDisconnect) as info,
        client.websocket_connect(url, headers=headers) as ws,
    ):
        ws.receive_bytes()
    return info.value.code


# ----------------------------------------------------------------------------- tickets


async def test_terminal_needs_a_valid_ticket_for_this_attempt(gateway, seeded) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = gateway
    attempt = await make_attempt(seeded)
    other = await make_attempt(seeded)
    base = f"/gw/v1/attempts/{attempt}/terminal"
    assert close_code(client, base) == 4401  # no ticket
    assert close_code(client, f"{base}?ticket=made-up") == 4401
    assert (
        close_code(client, f"{base}?ticket={ticket_for(client, other)}") == 4401
    )  # another attempt
    assert close_code(client, f"{base}?ticket={ticket_for(client, attempt, 'telemetry')}") == 4401


async def test_tickets_are_single_use(gateway, seeded) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = gateway
    attempt = await make_attempt(seeded)
    ticket = ticket_for(client, attempt)
    url = f"/gw/v1/attempts/{attempt}/terminal?ticket={ticket}"
    with client.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
        ws.send_bytes(b"x")
        assert ws.receive_bytes() == b"echo:x"
    assert close_code(client, url) == 4401  # reused


async def test_tickets_expire(gateway, seeded) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = gateway
    attempt = await make_attempt(seeded)
    ticket = ticket_for(client, attempt, ttl=1)
    await asyncio.sleep(1.5)
    assert close_code(client, f"/gw/v1/attempts/{attempt}/terminal?ticket={ticket}") == 4401


async def test_foreign_origins_are_refused(gateway, seeded) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = gateway
    attempt = await make_attempt(seeded)
    url = f"/gw/v1/attempts/{attempt}/terminal?ticket={ticket_for(client, attempt)}"
    assert close_code(client, url, origin="https://evil.example") == 4403


async def test_terminal_waits_for_the_sandbox(gateway, seeded) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = gateway
    attempt = await make_attempt(seeded, AttemptState.PROVISIONING)
    assert (
        close_code(
            client, f"/gw/v1/attempts/{attempt}/terminal?ticket={ticket_for(client, attempt)}"
        )
        == 4409
    )
    ended = await make_attempt(seeded, AttemptState.EXPIRED)
    assert (
        close_code(client, f"/gw/v1/attempts/{ended}/terminal?ticket={ticket_for(client, ended)}")
        == 4410
    )


# ---------------------------------------------------------------------------- terminal


async def test_terminal_bridges_keys_resizes_and_records(gateway, seeded) -> None:  # type: ignore[no-untyped-def]
    client, driver, store = gateway
    attempt = await make_attempt(seeded)
    url = (
        f"/gw/v1/attempts/{attempt}/terminal?ticket={ticket_for(client, attempt)}&cols=100&rows=30"
    )
    with client.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
        ws.send_bytes(b"ls\r")
        assert ws.receive_bytes() == b"echo:ls\r"
        ws.send_text(json.dumps({"type": "resize", "cols": 140, "rows": 40}))
        ws.send_text(json.dumps({"type": "ping", "t": 1}))
        assert json.loads(ws.receive_text()) == {"type": "pong", "t": 1}
        ws.send_bytes(b"x" * (64 * 1024 + 1))
        with pytest.raises(WebSocketDisconnect) as too_big:
            ws.receive_bytes()
        assert too_big.value.code == 1009
    pty = driver.ptys[0]
    assert pty.sizes == [(100, 30), (140, 40)]
    assert pty.closed
    for _ in range(50):
        if store.objects:
            break
        await asyncio.sleep(0.05)
    [(key, cast)] = store.objects.items()
    assert key.startswith(f"recordings/{attempt}/terminal-")
    header, *events = cast.decode().splitlines()
    assert json.loads(header)["width"] == 100
    assert any(json.loads(e)[2] == "echo:ls\r" for e in events)
    rows: list[Recording] = []
    for _ in range(50):  # the row is written just after the upload
        rows = list(
            (await seeded.scalars(select(Recording).where(Recording.attempt_id == attempt))).all()
        )
        if rows:
            break
        await asyncio.sleep(0.05)
    assert len(rows) == 1
    assert rows[0].bytes == len(cast)


async def test_telemetry_sends_hello_history_and_logs(gateway, seeded) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = gateway
    attempt = await make_attempt(seeded)
    assert client.portal is not None
    valkey = client.app.state.valkey  # type: ignore[attr-defined]
    client.portal.call(
        valkey.lpush,
        f"attempt:{attempt}:samples",
        json.dumps({"t": 1.0, "values": {"error_rate": 0.0}}),
    )
    url = f"/gw/v1/attempts/{attempt}/telemetry?ticket={ticket_for(client, attempt, 'telemetry')}"
    with client.websocket_connect(url, headers={"origin": ORIGIN}) as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        assert "db_qps_product" in hello["metrics"]
        assert hello["slo"]["db_qps_product"] == {"lt": 75.0}
        history = ws.receive_json()
        assert history == {
            "type": "history",
            "samples": [{"t": 1.0, "values": {"error_rate": 0.0}}],
        }
        logs = ws.receive_json()
        assert logs["type"] == "logs"
        assert logs["lines"][0]["service"] == "api"
        # Close from our side first, so the handler ends on the disconnect rather than being
        # cancelled by the test client mid-cleanup.
        ws.close()


# ---------------------------------------------------------------------------- internal


def signed_call(client: TestClient, method: str, target: str, body: dict[str, Any] | None = None):
    content = json.dumps(body).encode() if body is not None else b""
    headers = signed_headers(SECRET, method, target, content)
    if body is not None:
        headers["content-type"] = "application/json"
    return client.request(method, target, content=content, headers=headers)


async def test_internal_calls_need_a_matching_signature(gateway, seeded) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = gateway
    attempt = await make_attempt(seeded)
    assert client.get(f"/internal/attempts/{attempt}/status").status_code == 401
    # A signature for one path doesn't open another.
    headers = signed_headers(SECRET, "GET", f"/internal/attempts/{attempt}/status", b"")
    assert client.get(f"/internal/attempts/{attempt}/files", headers=headers).status_code == 401
    assert (
        signed_call(client, "GET", f"/internal/attempts/{attempt}/status").json()["services"][0][
            "name"
        ]
        == "api"
    )
    assert (
        signed_call(client, "GET", f"/internal/attempts/{uuid.uuid4()}/status").status_code == 404
    )


@pytest.mark.parametrize(
    "path", ["../../etc/passwd", "/etc/passwd", ".git/config", "app/../../x", "app/\x00"]
)
async def test_file_api_refuses_paths_outside_the_repo(gateway, seeded, path: str) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = gateway
    attempt = await make_attempt(seeded)
    from urllib.parse import urlencode

    res = signed_call(
        client, "GET", f"/internal/attempts/{attempt}/file?{urlencode({'path': path})}"
    )
    assert (res.status_code, res.json()["code"]) == (400, "bad_path")


async def test_restart_records_an_action_and_fires_beats(gateway, seeded) -> None:  # type: ignore[no-untyped-def]
    client, driver, _ = gateway
    attempt = await make_attempt(seeded)
    res = signed_call(client, "POST", f"/internal/attempts/{attempt}/restarts", {"service": "api"})
    assert res.json() == {"message": "api restarted"}
    assert driver.restarted == ["api"]
    events = (
        await seeded.scalars(select(AttemptEvent).where(AttemptEvent.attempt_id == attempt))
    ).all()
    assert [(e.type, e.payload["verb"]) for e in events] == [("action", "restart")]
    bad = signed_call(
        client, "POST", f"/internal/attempts/{attempt}/restarts", {"service": "tools"}
    )
    assert bad.status_code == 404  # the shell isn't a service you restart


async def test_cli_dispatch(gateway, seeded) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = gateway
    attempt = await make_attempt(seeded)
    ops = client.app.state.ops  # type: ignore[attr-defined]
    assert client.portal is not None
    status, body = client.portal.call(dispatch, ops, attempt, {"method": "GET", "path": "/status"})
    assert status == 200 and body["services"][0]["name"] == "api"
    status, body = client.portal.call(
        dispatch, ops, attempt, {"method": "POST", "path": "/rollback", "body": {"sha": "nope"}}
    )
    assert status == 400
    status, body = client.portal.call(
        dispatch, ops, attempt, {"method": "DELETE", "path": "/everything"}
    )
    assert status == 404


def test_healthz(gateway) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = gateway
    assert client.get("/healthz").json()["status"] == "ok"


async def test_timed_beats_stay_quiet_once_mitigated(seeded) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from devgrill.infra.events import EventRecorder

    recorder = EventRecorder(async_sessionmaker(seeded.bind, expire_on_commit=False), None)
    # ttl-zero's first beat is timed (Priya at T+15s): it fires during the incident...
    active = await make_attempt(seeded)
    assert await recorder.beat(active, 0) is True
    # ...but nobody asks about a problem that's already mitigated.
    for state in (AttemptState.MITIGATED, AttemptState.RESOLVED):
        assert await recorder.beat(await make_attempt(seeded, state), 0) is False
