"""Smoke test a running stack: api readiness, gateway health, web root, Temporal ping workflow.

Start the stack first (`just dev`, or the CI services), then run `just smoke`.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8000"
GATEWAY = "http://127.0.0.1:8100"
WEB = "http://127.0.0.1:3000"


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 (fixed local URLs)
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", errors="replace")


def _wait(name: str, url: str, accept: int = 200, timeout_s: float = 90) -> str:
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while time.monotonic() < deadline:
        try:
            status, body = _get(url)
            if status == accept:
                print(f"  ok   {name}: {url} → {status}")
                return body
            last = f"{status} {body[:200]}"
        except OSError as exc:
            last = type(exc).__name__
        time.sleep(1)
    print(f"  FAIL {name}: {url} → {last}")
    raise SystemExit(1)


async def _ping() -> str:
    from devgrill_worker.__main__ import run_ping

    return await asyncio.wait_for(run_ping("smoke"), timeout=30)


def main() -> int:
    print("smoke:")
    ready = json.loads(_wait("api /readyz", f"{API}/readyz"))
    for dep, result in ready["checks"].items():
        print(f"         {dep}: ok={result['ok']} {result['latency_ms']}ms")
    _wait("gateway /healthz", f"{GATEWAY}/healthz")
    page = _wait("web /", f"{WEB}/")
    if "DevGrill" not in page:
        print("  FAIL web /: page does not contain the brand name")
        return 1
    result = asyncio.run(_ping())
    if result != "pong:smoke":
        print(f"  FAIL temporal ping: {result!r}")
        return 1
    print(f"  ok   temporal PingWorkflow → {result}")
    print("smoke: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
