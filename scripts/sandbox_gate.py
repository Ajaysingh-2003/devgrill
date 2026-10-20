"""Phase 3 sandbox gate evidence (docs/qc/phase-3.md, docs/perf/phase-3.md).

  isolation      egress, platform reachability, fork bomb, memory hog
  timing [-n 5]  time to active (boot + faults + load), as an attempt does it
  leaks [-n 50]  N create -> destroy cycles; nothing may be left behind

Run as `uv run python scripts/sandbox_gate.py <check>`.

Needs Docker and the platform stack (`just deps-up`, for the reachability check). Prints a
JSON summary and exits non-zero if a check fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import aiodocker

from devgrill.sandbox.compose import ComposeDriver
from devgrill.sandbox.content import Bundle, load_bundle
from devgrill.sandbox.driver import SandboxHandle, SandboxSpec

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "ttl-zero"


def driver() -> ComposeDriver:
    return ComposeDriver(probe_build_dir=ROOT / "infra/sandbox/probe")


async def boot(d: ComposeDriver, bundle: Bundle, *, play: bool) -> tuple[SandboxHandle, float]:
    started = time.monotonic()
    handle = await d.create(SandboxSpec(f"gate-{uuid.uuid4()}", bundle))
    if play:
        for step in sorted(bundle.scenario.faults, key=lambda s: s.at_seconds):
            if step.at_seconds <= 0:
                await d.apply_fault(handle, bundle, step.use, dict(step.params))
        await d.start_load(handle, bundle)
    return handle, time.monotonic() - started


async def platform_ips() -> list[str]:
    """IPs of the platform's own containers (Postgres, Valkey, Temporal...)."""
    docker = aiodocker.Docker()
    try:
        ips = []
        for c in await docker.containers.list(filters=json.dumps({"name": ["devgrill-dev"]})):
            info = await c.show()
            for net in (info["NetworkSettings"].get("Networks") or {}).values():
                if net.get("IPAddress"):
                    ips.append(net["IPAddress"])
        return ips
    finally:
        await docker.close()


async def isolation() -> dict[str, Any]:
    d = driver()
    bundle = load_bundle(ROOT / "content", SCENARIO)
    handle, _ = await boot(d, bundle, play=False)
    shell = bundle.base_app.shell_service
    checks: dict[str, Any] = {}
    try:

        async def sh(cmd: str, limit_s: int = 60) -> tuple[int, str]:
            r = await d.exec(handle, shell, ["sh", "-c", cmd], timeout_s=limit_s)
            return r.exit_code, (r.stdout + r.stderr).strip()

        code, _ = await sh("curl -sS -m 5 https://example.com -o /dev/null")
        checks["egress_dns_blocked"] = code != 0
        code, _ = await sh("curl -sS -m 5 http://1.1.1.1 -o /dev/null")
        checks["egress_ip_blocked"] = code != 0
        code, _ = await sh("curl -sS -m 5 http://host.docker.internal:5432 -o /dev/null")
        checks["host_unreachable"] = code != 0
        reachable = []
        for ip in await platform_ips():
            code, _ = await sh(f"timeout 4 bash -c 'echo > /dev/tcp/{ip}/5432' 2>/dev/null")
            if code == 0:
                reachable.append(ip)
        checks["platform_containers_unreachable"] = not reachable

        # Fork bomb: it fills the shell's pids_limit and stops there; other containers keep
        # serving. The bomb outlives `timeout` (its children keep forking), so the shell is
        # restarted afterwards, as the platform would do.
        await sh("timeout 10 bash -c ':(){ :|:& };:' >/dev/null 2>&1; true", limit_s=30)
        stuck = await d.exec(handle, shell, ["true"], timeout_s=10)
        api_ok = await d.probe(handle, ["curl", "-fsS", "-m", "5", "http://api:8000/healthz"])
        checks["fork_bomb_filled_only_the_shell"] = not stuck.ok
        checks["fork_bomb_contained"] = api_ok.ok
        await d.restart(handle, shell)
        await asyncio.sleep(2)
        checks["shell_recovers_after_restart"] = (await d.exec(handle, shell, ["true"])).ok

        # Memory hog: the shell is OOM-killed (137); the API is untouched.
        code, _ = await sh("python3 -c 'x = bytearray(2 * 1024 ** 3)'", limit_s=60)
        api_ok = await d.probe(handle, ["curl", "-fsS", "-m", "5", "http://api:8000/healthz"])
        checks["memory_hog_exit_code"] = code
        checks["memory_hog_contained"] = code == 137 and api_ok.ok
    finally:
        await d.destroy(handle)
        await d.close()
    checks["ok"] = all(v for k, v in checks.items() if isinstance(v, bool))
    return checks


async def timing(n: int) -> dict[str, Any]:
    d = driver()
    bundle = load_bundle(ROOT / "content", SCENARIO)
    await d.ensure_images(bundle)
    times = []
    try:
        for _ in range(n):
            handle, seconds = await boot(d, bundle, play=True)
            times.append(round(seconds, 1))
            await d.destroy(handle)
    finally:
        await d.close()
    return {
        "runs": times,
        "p50_s": statistics.median(times),
        "max_s": max(times),
        "ok": max(times) < 45,
    }


async def leaks(n: int) -> dict[str, Any]:
    d = driver()
    bundle = load_bundle(ROOT / "content", SCENARIO)
    await d.ensure_images(bundle)
    before = await d.count_resources()
    failures = 0
    started = time.monotonic()
    try:
        for i in range(n):
            handle = None
            try:
                handle, _ = await boot(d, bundle, play=False)
            except Exception as exc:
                failures += 1
                print(f"cycle {i}: boot failed: {exc}", file=sys.stderr)
            finally:
                if handle is not None:
                    await d.destroy(handle)
            if (i + 1) % 10 == 0:
                print(f"{i + 1}/{n} cycles", file=sys.stderr)
        after = await d.count_resources()
        leftover = await d.list_sandboxes()
    finally:
        await d.close()
    return {
        "cycles": n,
        "boot_failures": failures,
        "minutes": round((time.monotonic() - started) / 60, 1),
        "before": before,
        "after": after,
        "leftover_sandboxes": leftover,
        "ok": after["containers"] == 0
        and after["networks"] == 0
        and after["dangling_volumes"] <= before["dangling_volumes"]
        and not leftover,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("check", choices=["isolation", "timing", "leaks"])
    parser.add_argument("-n", type=int, default=None)
    args = parser.parse_args()
    if args.check == "isolation":
        result = asyncio.run(isolation())
    elif args.check == "timing":
        result = asyncio.run(timing(args.n or 5))
    else:
        result = asyncio.run(leaks(args.n or 50))
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
