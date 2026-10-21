"""Test helpers shipped with the package: a stand-in for Better Auth's signing keys.

Lives in src (not tests/) so module-scoped fixtures and helpers can import it directly.
Never used by the running app.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm
from sqlalchemy import update

from devgrill.domain.enums import AttemptState
from devgrill.infra.models import Attempt
from devgrill_api.errors import AppError

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


# ------------------------------------------------------------ workspace and debrief tests


class FakeOrchestrator:
    def __init__(self) -> None:
        self.signals: list[tuple[str, str]] = []

    async def start(self, inp: Any) -> None:
        return None

    async def signal(self, attempt_id: str, name: str) -> None:
        self.signals.append((attempt_id, name))


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
