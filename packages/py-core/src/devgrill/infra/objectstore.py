"""A minimal S3 client (PutObject, GetObject, CreateBucket) with AWS Signature V4.

Recordings are the only objects so far; a full SDK (boto) is a lot of weight for two calls.
Works with SeaweedFS locally and any S3-compatible store (path-style URLs).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

import httpx2

if TYPE_CHECKING:
    from devgrill.config import Settings


class ObjectStoreError(RuntimeError):
    pass


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


@dataclass(frozen=True, slots=True)
class ObjectStore:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    region: str = "us-east-1"

    @classmethod
    def from_settings(cls, settings: Settings) -> ObjectStore:
        return cls(
            settings.s3_endpoint,
            settings.s3_access_key,
            settings.s3_secret_key,
            settings.s3_bucket,
            settings.s3_region,
        )

    def _signed(
        self, method: str, path: str, body: bytes, now: datetime | None = None
    ) -> tuple[str, dict[str, str]]:
        now = now or datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        day = now.strftime("%Y%m%d")
        host = urlsplit(self.endpoint).netloc
        payload_hash = hashlib.sha256(body).hexdigest()
        canonical_path = quote(path, safe="/-_.~")
        headers = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
        signed_names = ";".join(sorted(headers))
        canonical = "\n".join(
            [
                method,
                canonical_path,
                "",
                "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)),
                signed_names,
                payload_hash,
            ]
        )
        scope = f"{day}/{self.region}/s3/aws4_request"
        to_sign = "\n".join(
            ["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()]
        )
        key = _hmac(
            _hmac(_hmac(_hmac(f"AWS4{self.secret_key}".encode(), day), self.region), "s3"),
            "aws4_request",
        )
        signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
        headers["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_names}, Signature={signature}"
        )
        headers.pop("host")
        return f"{self.endpoint.rstrip('/')}{canonical_path}", headers

    async def _request(self, method: str, path: str, body: bytes = b"") -> httpx2.Response:
        url, headers = self._signed(method, path, body)
        async with httpx2.AsyncClient(timeout=30) as client:
            return await client.request(method, url, content=body, headers=headers)

    async def ensure_bucket(self) -> None:
        res = await self._request("PUT", f"/{self.bucket}")
        if res.status_code not in (200, 409):  # 409: it already exists
            raise ObjectStoreError(f"create bucket: {res.status_code} {res.text[:200]}")

    async def put(self, key: str, data: bytes) -> None:
        res = await self._request("PUT", f"/{self.bucket}/{key}", data)
        if res.status_code == 404 and b"NoSuchBucket" in res.content:
            await self.ensure_bucket()
            res = await self._request("PUT", f"/{self.bucket}/{key}", data)
        if res.status_code != 200:
            raise ObjectStoreError(f"put {key}: {res.status_code} {res.text[:200]}")

    async def get(self, key: str) -> bytes:
        res = await self._request("GET", f"/{self.bucket}/{key}")
        if res.status_code != 200:
            raise ObjectStoreError(f"get {key}: {res.status_code}")
        return res.content
