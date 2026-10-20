"""devgrill-content: validate, build, play and test scenarios; publish them to the database.

list                  scenarios under content/scenarios
validate [slug]       every content file, and every cross-reference (no Docker needed)
schema [--out DIR]    JSON Schema for scenario.yaml, fault.yaml, ... (editor autocompletion)
build [slug]          build the base-app and probe images a scenario needs
up <slug>             boot a scenario locally with its faults and load; Ctrl+C tears it down
test [slug]           break → fix → verify check (ADR 012); all playable scenarios by default
publish / seed        load tracks, topics and scenarios into the database
sandboxes [--sweep]   list sandboxes left on this machine (and remove them)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

from devgrill_content import __version__

CONTENT_ROOT = Path("content")
PROBE_BUILD_DIR = Path("infra/sandbox/probe")


def list_scenarios(root: Path = CONTENT_ROOT) -> list[Path]:
    """Every folder under content/scenarios that contains a scenario.yaml."""
    return sorted(p.parent for p in (root / "scenarios").glob("*/*/scenario.yaml"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="devgrill-content",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--root", type=Path, default=CONTENT_ROOT, help="content folder")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list scenarios")
    for name in ("seed", "publish"):
        sub.add_parser(name, help="load content into the database")
    for name in ("validate", "build", "test"):
        sub.add_parser(name).add_argument("slug", nargs="?")
    sub.add_parser("up").add_argument("slug")
    sub.add_parser("schema").add_argument("--out", type=Path, default=Path("content/.schema"))
    sub.add_parser("sandboxes").add_argument("--sweep", action="store_true")

    args = parser.parse_args(argv)
    root: Path = args.root
    match args.command:
        case "list":
            for path in list_scenarios(root):
                print(path.as_posix())
            return 0
        case "seed" | "publish":
            if validate(root) != 0:
                return 1
            return asyncio.run(_seed(root))
        case "validate":
            return validate(root, args.slug)
        case "schema":
            return write_schema(args.out)
        case "build":
            return asyncio.run(_build(root, args.slug))
        case "up":
            return asyncio.run(_up(root, args.slug))
        case "test":
            return asyncio.run(_test(root, args.slug))
        case "sandboxes":
            return asyncio.run(_sandboxes(args.sweep))
    return 2


# ------------------------------------------------------------------------------ validate


def validate(root: Path, slug: str | None = None) -> int:
    from pydantic import ValidationError

    from devgrill.domain.spec import FaultSpec, ScenarioSpec, TracksFile
    from devgrill.sandbox.baseapp import load_base_app
    from devgrill.sandbox.content import ContentError, load_bundle, load_yaml
    from devgrill_content.patchcheck import check_fault, check_scenario
    from devgrill_content.scenario_test import load_solution

    errors: list[str] = []

    def attempt[T](label: str, fn: Callable[[], T]) -> T | None:
        try:
            return fn()
        except (ValidationError, ContentError, ValueError, OSError) as exc:
            errors.append(f"{label}: {exc}")
            return None

    attempt("tracks.yaml", lambda: TracksFile.model_validate(load_yaml(root / "tracks.yaml")))
    apps = []
    for folder in sorted((root / "base-apps").glob("*/base-app.yaml")):
        loaded = attempt(
            f"base-app {folder.parent.name}", lambda f=folder: load_base_app(root, f.parent.name)
        )
        if loaded is not None:
            apps.append(loaded)
    for path in sorted((root / "faults").glob("*/*/fault.yaml")):
        ref = f"{path.parent.parent.name}/{path.parent.name}"
        if attempt(f"fault {ref}", lambda p=path: FaultSpec.model_validate(load_yaml(p))) is None:
            continue
        for app_dir, app in apps:
            errors.extend(
                attempt(f"fault {ref}", lambda r=ref, a=app, d=app_dir: check_fault(root, a, d, r))
                or []
            )
    checked = 0
    for folder in list_scenarios(root):
        if slug and folder.name != slug:
            continue
        checked += 1
        spec = attempt(
            f"scenario {folder.name}",
            lambda f=folder: ScenarioSpec.model_validate(load_yaml(f / "scenario.yaml")),
        )
        if isinstance(spec, ScenarioSpec) and spec.playable and spec.faults:
            bundle = attempt(f"scenario {folder.name}", lambda f=folder: load_bundle(root, f.name))
            if bundle is not None:
                solution = attempt(
                    f"scenario {folder.name} solution", lambda b=bundle: load_solution(b)
                )
                if solution is not None:
                    solution_dir, solution_spec = solution
                    patches = [(s.service, s.patch) for s in solution_spec.steps if s.patch]
                    errors.extend(check_scenario(bundle, solution_dir, patches))
    if slug and not checked:
        errors.append(f"no scenario {slug!r}")
    for line in errors:
        print(f"✗ {line}", file=sys.stderr)
    print(f"validate: {checked} scenarios checked, {len(errors)} problems")
    return 1 if errors else 0


def write_schema(out: Path) -> int:
    from devgrill.domain.spec import ApproachSpec, FaultSpec, ScenarioSpec, SolutionSpec, TracksFile
    from devgrill.sandbox.baseapp import BaseAppSpec

    out.mkdir(parents=True, exist_ok=True)
    models = {
        "scenario": ScenarioSpec,
        "fault": FaultSpec,
        "approach": ApproachSpec,
        "solution": SolutionSpec,
        "base-app": BaseAppSpec,
        "tracks": TracksFile,
    }
    for name, model in models.items():
        schema = model.model_json_schema(by_alias=True)
        (out / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    print(f"schema: wrote {len(models)} schemas to {out.as_posix()}")
    return 0


# ---------------------------------------------------------------------------- sandboxes


def _driver():
    from devgrill.sandbox.compose import ComposeDriver

    return ComposeDriver(probe_build_dir=PROBE_BUILD_DIR)


def _playable(root: Path, slug: str | None) -> list[str]:
    from devgrill.domain.spec import ScenarioSpec
    from devgrill.sandbox.content import load_yaml

    folders = list_scenarios(root)
    if slug is not None:
        return [f.name for f in folders if f.name == slug]
    slugs = []
    for folder in folders:
        spec = ScenarioSpec.model_validate(load_yaml(folder / "scenario.yaml"))
        if spec.playable and spec.faults:
            slugs.append(folder.name)
    return slugs


async def _build(root: Path, slug: str | None) -> int:
    from devgrill.sandbox.content import load_bundle

    driver = _driver()
    try:
        for name in _playable(root, slug):
            started = time.monotonic()
            await driver.ensure_images(load_bundle(root, name))
            print(f"build: {name} images ready ({time.monotonic() - started:.0f}s)")
    finally:
        await driver.close()
    return 0


async def _up(root: Path, slug: str) -> int:
    import uuid

    from devgrill.sandbox.content import load_bundle
    from devgrill.sandbox.driver import SandboxSpec
    from devgrill.sandbox.verifier import Verifier

    bundle = load_bundle(root, slug)
    driver = _driver()
    handle = None
    try:
        started = time.monotonic()
        handle = await driver.create(SandboxSpec(f"up-{uuid.uuid4()}", bundle))
        for step in sorted(bundle.scenario.faults, key=lambda s: s.at_seconds):
            if step.at_seconds <= 0:
                await driver.apply_fault(handle, bundle, step.use, dict(step.params))
        await driver.start_load(handle, bundle)
        print(f"up: {slug} is live in {time.monotonic() - started:.0f}s")
        if bundle.scenario.page:
            print(f"    PAGE [{bundle.scenario.page.severity}] {bundle.scenario.page.title}")
        print(f"    shell: docker exec -it {handle.ref}-{bundle.base_app.shell_service} bash -l")
        print("    Ctrl+C tears it down.")
        verifier = Verifier(driver, handle, bundle)
        prev = await verifier.scrape()
        while True:
            await asyncio.sleep(10)
            cur = await verifier.scrape()
            values = verifier.values(prev, cur)
            prev = cur
            shown = ", ".join(f"{k}={v:.3g}" for k, v in values.items() if v is not None)
            print(f"    {time.strftime('%H:%M:%S')} {shown}")
    except KeyboardInterrupt, asyncio.CancelledError:
        print("up: tearing down")
    finally:
        if handle is not None:
            await asyncio.shield(driver.destroy(handle))
        await driver.close()
    return 0


async def _test(root: Path, slug: str | None) -> int:
    from devgrill.sandbox.content import ContentError, load_bundle
    from devgrill_content.scenario_test import run_test, save_report

    slugs = _playable(root, slug)
    if not slugs:
        print("test: no playable scenarios", file=sys.stderr)
        return 1
    driver = _driver()
    failed = []
    try:
        for name in slugs:
            print(f"test: {name}")
            try:
                bundle = load_bundle(root, name)
            except (ContentError, ValueError) as exc:
                print(f"test: {name} FAIL {exc}", file=sys.stderr)
                failed.append(name)
                continue
            report = await run_test(bundle, driver)
            path = save_report(root, report)
            print(
                f"test: {name} {'PASS' if report.ok else 'FAIL ' + report.error}"
                f" ({path.as_posix()})"
            )
            if not report.ok:
                failed.append(name)
    finally:
        await driver.close()
    return 1 if failed else 0


async def _sandboxes(sweep: bool) -> int:
    from devgrill.sandbox.driver import SandboxHandle

    driver = _driver()
    try:
        refs = await driver.list_sandboxes()
        for ref in refs:
            print(ref)
            if sweep:
                await driver.destroy(SandboxHandle(attempt_id="", ref=ref))
        print(
            f"sandboxes: {len(refs)}{' removed' if sweep else ''};"
            f" leftovers {await driver.count_resources()}"
        )
    finally:
        await driver.close()
    return 0


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
