"""Test helpers shipped with the package: a stand-in for Better Auth's signing keys.

Lives in src (not tests/) so module-scoped fixtures and helpers can import it directly.
Never used by the running app.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm
from sqlalchemy import update

from devgrill.domain.enums import AttemptState, VerifyStatus
from devgrill.infra.models import Attempt, AttemptEvent, VerifyRun
from devgrill.sandbox.content import load_approaches, load_bundle
from devgrill_api.errors import AppError
from devgrill_api.orchestrator import OrchestratorError

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncSession

ISSUER = "http://localhost:3000"
#: The repository's content folder (integration tests seed from it).
CONTENT = Path(__file__).resolve().parents[4] / "content"
AUDIENCE = "devgrill-api"


@dataclass
class Signer:
    """Stands in for Better Auth: an Ed25519 key set that can rotate, and a token minter."""

    keys: dict[str, Ed25519PrivateKey] = field(default_factory=dict)
    published: list[str] = field(default_factory=list)
    fetches: int = 0

    def rotate(self) -> str:
        kid = uuid.uuid4().hex
        self.keys[kid] = Ed25519PrivateKey.generate()
        self.published.append(kid)
        return kid

    def jwks(self) -> dict[str, Any]:
        keys = []
        for kid in self.published:
            jwk = json.loads(OKPAlgorithm.to_jwk(self.keys[kid].public_key()))
            keys.append({**jwk, "kid": kid, "alg": "EdDSA", "use": "sig"})
        return {"keys": keys}

    async def fetch(self) -> dict[str, Any]:
        self.fetches += 1
        return self.jwks()

    def token(
        self,
        sub: str | uuid.UUID | None = None,
        *,
        kid: str | None = None,
        exp_in: int = 900,
        aud: str = AUDIENCE,
        iss: str = ISSUER,
        **claims: Any,
    ) -> str:
        kid = kid or self.published[-1]
        now = int(time.time())
        payload = {
            "sub": str(sub or uuid.uuid4()),
            "iss": iss,
            "aud": aud,
            "iat": now,
            "exp": now + exp_in,
            **claims,
        }
        return jwt.encode(payload, self.keys[kid], algorithm="EdDSA", headers={"kid": kid})


def make_signer() -> Signer:
    signer = Signer()
    signer.rotate()
    return signer


class NullOrchestrator:
    """Accepts every start and signal and does nothing (contract tests: no real sandboxes)."""

    async def start(self, inp: object) -> None:
        return None

    async def signal(self, attempt_id: str, name: str) -> None:
        return None

    async def review(self, attempt_id: str) -> None:
        return None


# ------------------------------------------------------------ workspace and debrief tests


class FakeOrchestrator:
    def __init__(self) -> None:
        self.signals: list[tuple[str, str]] = []
        self.reviews: list[str] = []
        self.fail_reviews = False

    async def start(self, inp: Any) -> None:
        return None

    async def signal(self, attempt_id: str, name: str) -> None:
        self.signals.append((attempt_id, name))

    async def review(self, attempt_id: str) -> None:
        if self.fail_reviews:
            raise OrchestratorError("temporal unreachable")
        self.reviews.append(attempt_id)


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str] | None, dict[str, Any] | None]] = []
        self.fail: AppError | None = None

    async def call(self, method: str, attempt_id: uuid.UUID, path: str, *, query=None, body=None):
        self.calls.append((method, path, query, body))
        if self.fail is not None:
            raise self.fail
        return {
            ("GET", "status"): {
                "services": [
                    {
                        "name": "api",
                        "state": "running",
                        "health": "healthy",
                        "restarts": 0,
                        "oom_killed": False,
                        "started_at": None,
                    }
                ]
            },
            ("GET", "files"): {"service": "api", "files": ["app/main.py"]},
            ("GET", "file"): {"service": "api", "path": "app/main.py", "content": "x = 1\n"},
            ("PUT", "file"): {"service": "api", "path": "app/main.py", "saved": True},
            ("POST", "deploys"): {
                "ok": True,
                "sha": "abc1234",
                "message": "api abc1234 is live",
                "log": "",
            },
            ("POST", "rollbacks"): {
                "ok": True,
                "sha": "1234abc",
                "message": "api 1234abc is live",
                "log": "",
            },
            ("POST", "restarts"): {"message": "api restarted"},
            ("GET", "db"): {
                "max_connections": 100,
                "connections": [{"state": "active", "n": 3}],
                "top": [
                    {"query": "SELECT 1", "calls": 5, "mean_ms": 0.1, "total_ms": 0.5, "rows": 5}
                ],
                "active": [],
            },
            ("POST", "db/query"): {"columns": ["n"], "rows": [[1]], "truncated": False, "ms": 1.0},
            ("GET", "cache"): {
                "stats": {
                    "hits": 1,
                    "misses": 9,
                    "hit_rate": 0.1,
                    "ops_per_sec": 5,
                    "used_memory": 1,
                    "maxmemory": 2,
                    "evicted_keys": 0,
                    "keys": 3,
                    "clients": 2,
                },
                "keys": [{"key": "product:1", "ttl": 30}],
                "asked": [{"key": "v2:product:1", "count": 9, "exists": False}],
                "window_s": 1.5,
            },
            ("GET", "deploys/abc1234"): {
                "service": "api",
                "sha": "abc1234" + "0" * 33,
                "short": "abc1234",
                "author": "ops-bot",
                "at": 1,
                "message": "config: use the new HA database endpoint",
                "files": ["config/app.env"],
                "diff": "-DATABASE_URL=a\n+DATABASE_URL=b\n",
            },
            ("GET", "deploys"): {
                "service": "api",
                "live": "abc",
                "live_dirty": False,
                "commits": [{"sha": "abc", "short": "abc", "author": "a", "at": 1, "message": "m"}],
            },
        }[(method, path)]


async def started(
    api: TestClient,
    seeded: AsyncSession,
    auth,
    slug: str = "ttl-zero",
    state: AttemptState = AttemptState.ACTIVE,
):  # type: ignore[no-untyped-def]
    user = uuid.uuid4()
    headers = auth(user, login=f"p-{user.hex[:6]}")
    res = api.post("/v1/attempts", json={"scenario_slug": slug}, headers=headers)
    assert res.status_code == 202, res.text
    attempt_id = uuid.UUID(res.json()["id"])
    await seeded.execute(update(Attempt).where(Attempt.id == attempt_id).values(state=state))
    await seeded.commit()
    return attempt_id, headers


# ------------------------------------------------------------------- finished attempts

PROBES = ["sale-replay", "db-offload", "honest-metrics", "correctness", "budget"]


def rules() -> list[tuple[str, Any]]:
    bundle = load_bundle(CONTENT, "ttl-zero")
    return [(s.key, s.match) for _, s in load_approaches(bundle) if not s.cheat]


async def finish(
    seeded: AsyncSession,
    attempt_id: uuid.UUID,
    *,
    state: AttemptState = AttemptState.RESOLVED,
    failing: tuple[str, ...] = (),
    rolled_back: bool = True,
    with_run: bool = True,
) -> None:
    """Make an attempt look played: 10 minutes, mitigated at 4, a verify run, an end state."""
    now = datetime.now(UTC)
    await seeded.execute(
        update(Attempt)
        .where(Attempt.id == attempt_id)
        .values(
            state=state,
            active_at=now - timedelta(minutes=10),
            mitigated_at=now - timedelta(minutes=6),
            ended_at=now,
        )
    )
    events: list[tuple[str, dict[str, Any]]] = [
        ("alert", {"severity": "SEV4", "title": "postgres: product reads 3x normal"}),
        ("trail", {"verb": "sql", "query": "select * from pg_stat_statements", "ok": True}),
        ("message", {"text": "Looking at the cache"}),
        ("message", {"text": "Rolled back the TTL change"}),
    ]
    if rolled_back:
        events.append(("rollback", {"service": "api", "ref": "abc", "sha": "abc", "ok": True}))
    for type_, payload in events:
        seeded.add(AttemptEvent(attempt_id=attempt_id, type=type_, payload=payload))
    if with_run:
        seeded.add(
            VerifyRun(
                attempt_id=attempt_id,
                status=VerifyStatus.FAILED if failing else VerifyStatus.PASSED,
                started_at=now - timedelta(minutes=2),
                finished_at=now,
                summary={
                    "probes": [
                        {
                            "key": key,
                            "kind": "load" if key != "correctness" else "hidden_test",
                            "title": key,
                            "how": "",
                            "weight": 0.5 if key == "budget" else 1.0,
                            "passed": key not in failing,
                            "detail": "",
                            "measured": {},
                        }
                        for key in PROBES
                    ]
                },
            )
        )
    await seeded.commit()
