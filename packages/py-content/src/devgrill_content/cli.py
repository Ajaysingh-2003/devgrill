"""devgrill-content CLI. Phase 0 ships the command surface; phase 3 implements the commands."""

from __future__ import annotations

import argparse
import asyncio
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
    seed_cmd = sub.add_parser("seed", help="load tracks, topics and scenarios into the database")
    seed_cmd.add_argument("--root", type=Path, default=CONTENT_ROOT)
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

    if args.command == "seed":
        return asyncio.run(_seed(args.root))

    print(f"devgrill-content {args.command}: not implemented yet (phase 3).", file=sys.stderr)
    return 2


async def _seed(root: Path) -> int:
    from devgrill.config import get_settings
    from devgrill.infra import db
    from devgrill_content.seed import ContentError, seed

    engine = db.create_engine(get_settings())
    try:
        async with db.create_session_factory(engine)() as session, session.begin():
            report = await seed(session, root)
    except ContentError as exc:
        print(f"seed: {exc}", file=sys.stderr)
        return 1
    finally:
        await engine.dispose()
    print(
        f"seed: {report.tracks} tracks, {report.topics} topics, "
        f"{report.scenarios_new} new scenarios, {report.versions_new} new versions, "
        f"{report.unchanged} unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
