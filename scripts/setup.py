"""One-time local setup checks: tools, Docker, .env. Run via `just setup`."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"git": "--version", "docker": "--version", "node": "--version", "pnpm": "--version"}


def _version(tool: str, flag: str) -> str | None:
    exe = shutil.which(tool)
    if exe is None:
        return None
    result = subprocess.run([exe, flag], capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip().splitlines()[0]


def main() -> int:
    ok = True
    print("setup: checking tools")
    for tool, flag in REQUIRED.items():
        version = _version(tool, flag)
        print(f"  {'ok  ' if version else 'MISS'} {tool}: {version or 'not found on PATH'}")
        ok &= version is not None

    docker = subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    running = docker.returncode == 0
    state = "running" if running else "start Docker Desktop"
    print(f"  {'ok  ' if running else 'MISS'} docker engine: {state}")
    ok &= running

    autocrlf = subprocess.run(
        ["git", "config", "core.autocrlf"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if autocrlf not in ("", "false", "input"):
        print(f"  WARN git core.autocrlf={autocrlf}; run: git config core.autocrlf false")

    if os.name == "nt" and "--use-system-ca" not in os.environ.get("NODE_OPTIONS", ""):
        print("  WARN NODE_OPTIONS lacks --use-system-ca (needed behind the corporate proxy)")

    env_file = ROOT / ".env"
    if not env_file.exists():
        env_file.write_text((ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
        print("  made .env from .env.example")
    else:
        print("  ok   .env exists")

    print("setup: ready" if ok else "setup: fix the MISS items above, then re-run `just setup`")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
