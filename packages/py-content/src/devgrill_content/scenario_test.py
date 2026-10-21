"""`devgrill-content test <slug>`: prove a scenario breaks, its fixes fix it, and cheats don't.

The reference fix runs the way a real attempt does (the SandboxLifecycle workflow):
  boot → faults due before T → load (T) → faults due after T
  → BREAKS: every fault's symptom contract shows, and the SLO is violated within 60 s
  → apply solution/ → MITIGATED: the SLO holds for its `for_s`
  → stop load → VERIFY: every probe passes, within the verify time budget
With `--approaches`, each `approaches/*.yaml` then gets a fresh sandbox: break, apply its
steps, verify, and compare with what it declares (ADR 015):
  full     every probe passes
  partial  exactly `fails_probes` fail
  fails    at least `fails_probes` fail (cheats always declare `fails`)
A cheat's step may be refused by the sandbox (e.g. resetting statistics without being a
superuser); that is recorded, and verify must still fail.
Reports go to content/.reports/<slug>.json (git-ignored).
"""

from __future__ import annotations

import asyncio
import json
import shlex
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from devgrill.domain.spec import ApproachSpec, SolutionSpec, SolutionStep
from devgrill.sandbox.compose import ComposeDriver
from devgrill.sandbox.content import Bundle, ContentError, load_approaches, load_yaml
from devgrill.sandbox.driver import SandboxError, SandboxHandle, SandboxSpec
from devgrill.sandbox.verifier import ProbeResult, Verifier, check

SLO_BREACH_WITHIN_S = 60
MITIGATION_WITHIN_S = 150
SAMPLE_EVERY_S = 5.0
#: Phase 5 gate: a verify run finishes within this.
VERIFY_BUDGET_S = 240
#: After an approach's last step: time for restarts and caches to settle before verify.
SETTLE_S = 20


@dataclass(slots=True)
class ApproachReport:
    key: str
    cheat: bool
    expected: str
    expected_failures: list[str]
    failed_probes: list[str] = field(default_factory=list)
    refused_steps: list[str] = field(default_factory=list)
    ok: bool = False
    verify_s: float | None = None
    error: str = ""


@dataclass(slots=True)
class Report:
    slug: str
    ok: bool = False
    stage: str = "boot"
    boot_s: float | None = None
    slo_breached_after_s: float | None = None
    symptoms: dict[str, float | None] = field(default_factory=dict)
    mitigated_after_s: float | None = None
    verify_s: float | None = None
    probes: list[dict[str, Any]] = field(default_factory=list)
    approaches: list[ApproachReport] = field(default_factory=list)
    samples: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


def load_solution(bundle: Bundle) -> tuple[Path, SolutionSpec]:
    folder = bundle.scenario_dir / "solution"
    path = folder / "solution.yaml"
    if not path.is_file():
        raise ContentError(f"{bundle.scenario.slug}: solution/solution.yaml is missing")
    spec = SolutionSpec.model_validate(load_yaml(path))
    for step in spec.steps:
        if step.patch and not (folder / step.patch).is_file():
            raise ContentError(f"{bundle.scenario.slug}: solution/{step.patch} is missing")
        if step.service not in bundle.base_app.services:
            raise ContentError(
                f"{bundle.scenario.slug}: solution step targets unknown {step.service}"
            )
    return folder, spec


def _round(values: dict[str, float | None]) -> dict[str, float | None]:
    return {k: (round(v, 4) if v is not None else None) for k, v in values.items()}


def judge(spec: ApproachSpec, failed: set[str]) -> bool:
    """Did verify give the outcome the approach declares?"""
    expected = set(spec.fails_probes)
    match spec.outcome:
        case "full":
            return not failed
        case "partial":
            return failed == expected
        case _:
            return bool(failed) and expected <= failed


async def apply_step(
    driver: ComposeDriver, handle: SandboxHandle, bundle: Bundle, folder: Path, step: SolutionStep
) -> str | None:
    """Apply one fix step; returns why it failed, or None."""
    if step.patch:
        deployed = await driver.patch(
            handle, bundle, step.service, (folder / step.patch).read_bytes(), step.message
        )
        return None if deployed.ok else f"patch {step.patch}: {deployed.message}"
    if step.rollback_to:
        shell = bundle.base_app.shell_service
        found = await driver.exec(
            handle,
            shell,
            [
                "sh",
                "-c",
                f"git -C /workspace/{step.service} log --format=%h -F"
                f" --grep={shlex.quote(step.rollback_to)} -1",
            ],
        )
        sha = found.stdout.strip()
        if not found.ok or not sha:
            return f"no commit {step.rollback_to!r} to roll back to"
        deployed = await driver.deploy(handle, bundle, step.service, ref=sha)
        return None if deployed.ok else f"rollback to {sha}: {deployed.message}"
    assert step.run is not None
    res = await driver.exec(handle, step.service, ["sh", "-c", step.run], timeout_s=120)
    return None if res.ok else f"{step.run[:80]}: {(res.stderr or res.stdout)[-300:]}"


async def _break(
    bundle: Bundle, driver: ComposeDriver, handle: SandboxHandle, verifier: Verifier, report: Report
) -> bool:
    """Faults and load, until the declared symptoms and an SLO breach show."""
    scenario = bundle.scenario
    assert scenario.slo is not None
    steps = sorted(scenario.faults, key=lambda s: s.at_seconds)
    for step in (s for s in steps if s.at_seconds <= 0):
        await driver.apply_fault(handle, bundle, step.use, dict(step.params))
    await driver.start_load(handle, bundle)
    t0 = time.monotonic()
    later = [s for s in steps if s.at_seconds > 0]
    pending = {bundle.faults[s.use].ref: bundle.faults[s.use].spec.symptom for s in steps}
    horizon = max([SLO_BREACH_WITHIN_S, *(c.within_s for c in pending.values())])
    prev = await verifier.scrape()
    while time.monotonic() - t0 < horizon:
        await asyncio.sleep(SAMPLE_EVERY_S)
        elapsed = time.monotonic() - t0
        while later and later[0].at_seconds <= elapsed:
            step = later.pop(0)
            await driver.apply_fault(handle, bundle, step.use, dict(step.params))
        cur = await verifier.scrape()
        values = verifier.values(prev, cur)
        prev = cur
        report.samples.append({"t": round(elapsed, 1), "phase": "break", **_round(values)})
        if report.slo_breached_after_s is None and check(scenario.slo.targets(), values):
            report.slo_breached_after_s = round(elapsed, 1)
        for ref, contract in list(pending.items()):
            value = values.get(contract.metric)
            if value is not None and (
                value > contract.value if contract.op == "gt" else value < contract.value
            ):
                report.symptoms[ref] = round(elapsed, 1)
                pending.pop(ref)
        if not pending and report.slo_breached_after_s is not None:
            break
    for ref in pending:
        report.symptoms[ref] = None
    return (
        report.slo_breached_after_s is not None
        and report.slo_breached_after_s <= SLO_BREACH_WITHIN_S
        and not pending
    )


async def run_test(bundle: Bundle, driver: ComposeDriver, *, echo: Any = print) -> Report:
    scenario = bundle.scenario
    report = Report(scenario.slug)
    if scenario.slo is None or scenario.load is None:
        report.error = "not playable: needs slo and load"
        return report
    solution_dir, solution = load_solution(bundle)
    started = time.monotonic()
    handle = await driver.create(SandboxSpec(f"test-{uuid.uuid4()}", bundle))
    verifier = Verifier(driver, handle, bundle)
    try:
        report.boot_s = round(time.monotonic() - started, 1)
        echo(f"  booted in {report.boot_s}s ({handle.ref})")

        report.stage = "break"
        broke = await _break(bundle, driver, handle, verifier, report)
        echo(f"  SLO breached after {report.slo_breached_after_s}s; symptoms {report.symptoms}")
        if not broke:
            report.error = "the scenario does not break as declared"
            return report

        report.stage = "fix"
        for fix in solution.steps:
            if err := await apply_step(driver, handle, bundle, solution_dir, fix):
                report.error = f"solution step failed: {err}"
                return report
            echo(f"  applied solution step: {fix.message}")

        # ---- mitigated: the SLO holds for for_s, within the limit
        report.stage = "mitigate"
        assert scenario.slo is not None
        t1 = time.monotonic()
        healthy_since: float | None = None
        prev = await verifier.scrape()
        while time.monotonic() - t1 < MITIGATION_WITHIN_S:
            await asyncio.sleep(SAMPLE_EVERY_S)
            cur = await verifier.scrape()
            values = verifier.values(prev, cur)
            prev = cur
            elapsed = time.monotonic() - t1
            report.samples.append({"t": round(elapsed, 1), "phase": "fix", **_round(values)})
            if check(scenario.slo.targets(), values):
                healthy_since = None
                continue
            healthy_since = healthy_since if healthy_since is not None else elapsed - SAMPLE_EVERY_S
            if elapsed - healthy_since >= scenario.slo.for_s:
                report.mitigated_after_s = round(healthy_since, 1)
                break
        echo(f"  mitigated after {report.mitigated_after_s}s")
        if report.mitigated_after_s is None:
            report.error = "the reference fix does not bring the SLO back"
            return report

        report.stage = "verify"
        await driver.stop_load(handle)
        t2 = time.monotonic()
        results: list[ProbeResult] = await verifier.run_all(scenario.probes)
        report.verify_s = round(time.monotonic() - t2, 1)
        report.probes = [asdict(r) for r in results]
        for r in results:
            echo(
                f"  probe {r.key}: {'PASS' if r.passed else 'FAIL'} {r.detail} {_round(r.measured)}"
            )
        echo(f"  verify took {report.verify_s}s")
        if not all(r.passed for r in results):
            report.error = "the reference fix fails probes"
            return report
        if report.verify_s > VERIFY_BUDGET_S:
            report.error = f"verify took {report.verify_s}s (budget {VERIFY_BUDGET_S}s)"
            return report
        report.ok = True
        report.stage = "done"
        return report
    except (SandboxError, ContentError) as exc:
        report.error = f"{report.stage}: {exc}"
        return report
    finally:
        await driver.destroy(handle)


async def run_approach(
    bundle: Bundle, driver: ComposeDriver, folder: Path, spec: ApproachSpec, *, echo: Any = print
) -> ApproachReport:
    """A fresh sandbox, broken; the approach's steps; verify; the declared outcome?"""
    out = ApproachReport(spec.key, spec.cheat, spec.outcome, list(spec.fails_probes))
    scratch = Report(bundle.scenario.slug)
    handle = await driver.create(SandboxSpec(f"test-{uuid.uuid4()}", bundle))
    verifier = Verifier(driver, handle, bundle)
    try:
        if not await _break(bundle, driver, handle, verifier, scratch):
            out.error = "the scenario did not break"
            return out
        for step in spec.steps:
            if err := await apply_step(driver, handle, bundle, folder, step):
                # Only a cheat's commands may be refused (tampering the sandbox blocks); a
                # patch that doesn't deploy is broken content, not a caught cheat.
                if not spec.cheat or step.run is None:
                    out.error = f"step failed: {err}"
                    return out
                out.refused_steps.append(err)
        await asyncio.sleep(SETTLE_S)
        await driver.stop_load(handle)
        started = time.monotonic()
        results = await verifier.run_all(bundle.scenario.probes)
        out.verify_s = round(time.monotonic() - started, 1)
        out.failed_probes = [r.key for r in results if not r.passed]
        out.ok = judge(spec, set(out.failed_probes))
        details = {r.key: r.detail for r in results if not r.passed}
        declared = spec.outcome + (f" {spec.fails_probes}" if spec.fails_probes else "")
        refused = f"; refused {out.refused_steps}" if out.refused_steps else ""
        echo(
            f"  {'cheat' if spec.cheat else 'approach'} {spec.key}: "
            f"{'OK' if out.ok else 'WRONG OUTCOME'} (declared {declared};"
            f" failed {out.failed_probes}{refused})"
        )
        for key, detail in details.items():
            echo(f"      {key}: {detail[:300]}")
        if not out.ok:
            out.error = (
                f"declared {spec.outcome} {spec.fails_probes}, verify failed {out.failed_probes}"
            )
        return out
    except (SandboxError, ContentError) as exc:
        out.error = str(exc)
        return out
    finally:
        await driver.destroy(handle)


async def run_approaches(
    bundle: Bundle,
    driver: ComposeDriver,
    report: Report,
    *,
    only: str | None = None,
    echo: Any = print,
) -> None:
    for folder, spec in load_approaches(bundle):
        if only and spec.key != only:
            continue
        report.approaches.append(await run_approach(bundle, driver, folder, spec, echo=echo))
    if bad := [a.key for a in report.approaches if not a.ok]:
        report.ok = False
        report.error = (report.error + "; " if report.error else "") + f"approaches: {bad}"


def save_report(content_root: Path, report: Report) -> Path:
    folder = content_root / ".reports"
    folder.mkdir(exist_ok=True)
    path = folder / f"{report.slug}.json"
    path.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8", newline="\n")
    return path
