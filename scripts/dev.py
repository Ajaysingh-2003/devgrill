"""Run api, worker, gateway and web together with prefixed output. Ctrl+C stops everything.

Processes are spawned directly (no shell): on this machine cmd.exe is blocked by policy,
which breaks tools like `concurrently`, so we avoid shells entirely.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_WINDOWS = os.name == "nt"
COLORS = {"api": "34", "worker": "35", "gateway": "36", "web": "32"}


@dataclass(frozen=True)
class Proc:
    name: str
    argv: list[str]
    cwd: Path


def _procs(only: set[str] | None) -> list[Proc]:
    node = shutil.which("node")
    if node is None:
        sys.exit("node not found on PATH")
    procs = [
        Proc("api", [sys.executable, "-m", "devgrill_api"], ROOT),
        Proc("worker", [sys.executable, "-m", "devgrill_worker"], ROOT),
        Proc("gateway", [sys.executable, "-m", "devgrill_gateway"], ROOT),
        Proc(
            "web",
            [node, "node_modules/next/dist/bin/next", "dev", "--port", "3000"],
            ROOT / "apps" / "web",
        ),
    ]
    return [p for p in procs if only is None or p.name in only]


def _pump(name: str, stream: object) -> None:
    color = COLORS.get(name, "37")
    prefix = f"\x1b[{color}m{name:>7} │\x1b[0m "
    for raw in iter(stream.readline, b""):  # type: ignore[attr-defined]
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        sys.stdout.write(prefix + line + "\n")
        sys.stdout.flush()


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if IS_WINDOWS:
        # uvicorn --reload and next dev spawn children; kill the whole tree.
        subprocess.run(  # noqa: S603
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],  # noqa: S607
            capture_output=True,
            check=False,
        )
    else:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)


def main() -> int:
    only = set(sys.argv[1:]) or None
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if "NO_COLOR" not in env:
        env["FORCE_COLOR"] = "1"
    procs = _procs(only)
    if any(p.name == "web" for p in procs):
        # The web app imports generated token CSS (packages/tokens/dist is git-ignored);
        # `next dev` does not run turbo builds, so generate it first (takes well under a second).
        build = [shutil.which("node") or "node", "packages/tokens/src/build.ts"]
        if subprocess.run(build, cwd=ROOT, check=False).returncode != 0:  # noqa: S603
            return 1
    running: list[tuple[Proc, subprocess.Popen[bytes]]] = []
    for spec in procs:
        proc = subprocess.Popen(  # noqa: S603
            spec.argv,
            cwd=spec.cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=not IS_WINDOWS,
        )
        threading.Thread(target=_pump, args=(spec.name, proc.stdout), daemon=True).start()
        running.append((spec, proc))

    print("dev: web http://localhost:3000 · api http://localhost:8000/docs · Ctrl+C to stop")
    exit_code = 0
    try:
        while True:
            for spec, proc in running:
                code = proc.poll()
                if code is not None:
                    print(f"dev: {spec.name} exited with {code}; stopping the rest")
                    exit_code = code or 1
                    raise KeyboardInterrupt
            threading.Event().wait(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for _, proc in running:
            _kill_tree(proc)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
