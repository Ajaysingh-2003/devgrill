"""Test helpers shipped with the package: a stand-in for Better Auth's signing keys.

Lives in src (not tests/) so module-scoped fixtures and helpers can import it directly.
Never used by the running app.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jwt.algorithms import OKPAlgorithm

ISSUER = "http://localhost:3000"
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
