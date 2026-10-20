"""End to end on the real stack: API -> Temporal -> worker -> Docker -> SSE (Phase 3 gate).

  uv run python scripts/attempt_e2e.py happy   guest starts ttl-zero, fixes it, verifies, resolved
  uv run python scripts/attempt_e2e.py crash   the worker is killed mid-provision; a new one
                                               takes over and the sandbox is still torn down

Starts its own API (port 8765) and worker processes on the dev database (`just deps-up`,
migrated and seeded). Prints a JSON summary; exits non-zero on failure.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx2 as httpx

from devgrill.sandbox.compose import ComposeDriver
from devgrill.sandbox.content import load_bundle
from devgrill.sandbox.driver import SandboxHandle
from devgrill_content.scenario_test import load_solution

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8765"
PYTHON = sys.executable


def spawn(module: str, extra_env: dict[str, str] | None = None) -> subprocess.Popen[bytes]:
    env = {**os.environ, "DEVGRILL_ENV": "dev", "PYTHONUTF8": "1", **(extra_env or {})}
    log = (ROOT / f".e2e-{module.split('.')[0]}.log").open("ab")
    return subprocess.Popen([PYTHON, "-m", module], cwd=ROOT, env=env, stdout=log, stderr=log)  # noqa: S603


def start_api() -> subprocess.Popen[bytes]:
    proc = spawn("devgrill_api", {"API_PORT": "8765", "DEVGRILL_ENV": "test"})
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{API}/healthz", timeout=2).status_code == 200:
                return proc
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    proc.kill()
    raise RuntimeError("API did not start (see .e2e-devgrill_api.log)")


def guest_headers(client: httpx.Client) -> dict[str, str]:
    token = client.post("/v1/guest-tokens").raise_for_status().json()["token"]
    return {"X-Guest-Token": token}


def wait_for_state(client: httpx.Client, url: str, headers: dict[str, str], states: set[str], timeout_s: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        body = client.get(url, headers=headers).raise_for_status().json()
        if body["state"] in states:
            return body
        time.sleep(1)
    raise TimeoutError(f"{url} never reached {states}")


def events(client: httpx.Client, attempt_id: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    """The whole SSE stream (it ends after the sandbox is destroyed)."""
    out = []
    with client.stream("GET", f"/v1/attempts/{attempt_id}/events", headers=headers, timeout=120) as res:
        for line in res.iter_lines():
            if line.startswith("data:"):
                out.append(json.loads(line[5:]))
    return out


async def leftovers() -> dict[str, int]:
    driver = ComposeDriver()
    try:
        return await driver.count_resources()
    finally:
        await driver.close()


def seconds_between(stream: list[dict[str, Any]], first: str, second: str) -> float | None:
    """Workflow time between two state events (excludes this script's process start-up)."""
    stamps = {e["payload"].get("to"): e["ts"] for e in stream if e["type"] == "state"}
    if first not in stamps or second not in stamps:
        return None
    from datetime import datetime

    return round((datetime.fromisoformat(stamps[second]) - datetime.fromisoformat(stamps[first])).total_seconds(), 1)


def torn_down(stream: list[dict[str, Any]]) -> bool:
    return any(e["type"] == "sandbox" and e["payload"].get("action") == "destroyed" for e in stream)


async def apply_solution(attempt_id: str, slug: str) -> None:
    """What a player would do in the shell: here, the reference fix."""
    bundle = load_bundle(ROOT / "content", slug)
    folder, solution = load_solution(bundle)
    driver = ComposeDriver()
    try:
        from devgrill.sandbox.compose import project_name

        handle = SandboxHandle(attempt_id, project_name(attempt_id))
        for step in solution.steps:
            assert step.patch
            result = await driver.patch(handle, bundle, step.service, (folder / step.patch).read_bytes(), step.message)
            assert result.ok, result
    finally:
        await driver.close()


def happy() -> dict[str, Any]:
    api, worker = start_api(), spawn("devgrill_worker")
    try:
        with httpx.Client(base_url=API, timeout=30) as client:
            headers = guest_headers(client)
            started = time.monotonic()
            res = client.post("/v1/attempts", json={"scenario_slug": "ttl-zero"}, headers=headers)
            assert res.status_code == 202, res.text
            attempt_id = res.json()["id"]
            url = f"/v1/attempts/{attempt_id}"
            active = wait_for_state(client, url, headers, {"active", "failed"}, 180)
            assert active["state"] == "active", active
            to_active = round(time.monotonic() - started, 1)
            time.sleep(20)  # let the incident show
            asyncio.run(apply_solution(attempt_id, "ttl-zero"))
            time.sleep(20)  # and the recovery
            assert client.post(f"{url}/verify", headers=headers).status_code == 202
            stream = events(client, attempt_id, headers)
            final = client.get(url, headers=headers).json()
        verify = next(e for e in stream if e["type"] == "verify")["payload"]
        return {
            "attempt": attempt_id,
            "time_to_active_s": seconds_between(stream, "provisioning", "active"),
            "time_to_active_incl_cold_worker_s": to_active,
            "torn_down": torn_down(stream),
            "final_state": final["state"],
            "verify_passed": verify["passed"],
            "probes": {p["key"]: p["passed"] for p in verify["probes"]},
            "event_types": [e["type"] for e in stream],
            "leftovers": asyncio.run(leftovers()),
            "ok": final["state"] == "resolved" and verify["passed"] and torn_down(stream),
        }
    finally:
        worker.kill()
        api.kill()


def crash() -> dict[str, Any]:
    api, worker = start_api(), spawn("devgrill_worker")
    replacement: subprocess.Popen[bytes] | None = None
    try:
        with httpx.Client(base_url=API, timeout=30) as client:
            headers = guest_headers(client)
            res = client.post("/v1/attempts", json={"scenario_slug": "ttl-zero"}, headers=headers)
            assert res.status_code == 202, res.text
            attempt_id = res.json()["id"]
            url = f"/v1/attempts/{attempt_id}"
            # Kill the worker hard once its sandbox containers exist (mid-provision).
            from devgrill.sandbox.compose import project_name

            ref = project_name(attempt_id)
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                names = subprocess.run(  # noqa: S603
                    ["docker", "ps", "-a", "--filter", f"label=devgrill.sandbox={ref}", "--format", "{{.Names}}"],  # noqa: S607
                    capture_output=True, text=True, check=False,
                ).stdout.split()
                if len(names) >= 3:
                    break
                time.sleep(0.5)
            worker.kill()
            killed_with = len(names)
            assert client.get(url, headers=headers).json()["state"] == "provisioning"
            replacement = spawn("devgrill_worker")
            active = wait_for_state(client, url, headers, {"active", "failed"}, 240)
            assert client.delete(url, headers=headers).status_code == 202
            stream = events(client, attempt_id, headers)
            final = client.get(url, headers=headers).json()
        return {
            "attempt": attempt_id,
            "containers_when_killed": killed_with,
            "state_after_takeover": active["state"],
            "final_state": final["state"],
            "torn_down": torn_down(stream),
            "leftovers": asyncio.run(leftovers()),
            "ok": active["state"] == "active" and final["state"] == "abandoned" and torn_down(stream),
        }
    finally:
        worker.kill()
        if replacement is not None:
            replacement.kill()
        api.kill()


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "happy"
    result = happy() if which == "happy" else crash()
    result["ok"] = result["ok"] and result["leftovers"]["containers"] == 0 and result["leftovers"]["networks"] == 0
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
