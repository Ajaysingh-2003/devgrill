"""devgrill-content CLI. Phase 0 ships the command surface; phase 3 implements the commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from devgrill_content import __version__

CONTENT_ROOT = Path("content")
PHASE_3_COMMANDS = ("validate", "build", "up", "test", "publish")


def list_scenarios(root: Path = CONTENT_ROOT) -> list[Path]:
    """Every folder under content/scenarios that contains a scenario.yaml."""
    return sorted(p.parent for p in (root / "scenarios").glob("*/*/scenario.yaml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="devgrill-content")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list scenarios found under content/scenarios")
    for name in PHASE_3_COMMANDS:
        cmd = sub.add_parser(name, help=f"{name} scenarios (phase 3)")
        cmd.add_argument("slug", nargs="?")

    args = parser.parse_args(argv)
    if args.command == "list":
        scenarios = list_scenarios()
        for path in scenarios:
            print(path.as_posix())
        if not scenarios:
            print("no scenarios yet (phase 3 adds the first three)")
        return 0

    print(f"devgrill-content {args.command}: not implemented yet (phase 3).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
