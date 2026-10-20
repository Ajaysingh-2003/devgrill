"""`devgrill-content test <slug>`: prove a scenario breaks and that its reference fix fixes it.

The same order as a real attempt (the SandboxLifecycle workflow):
  boot → faults due before T → load (T) → faults due after T
  → BREAKS: every fault's symptom contract shows, and the SLO is violated within 60 s
  → apply solution/ → MITIGATED: the SLO holds for its `for_s`
  → stop load → PROBES: every probe passes
The report is printed and written to content/.reports/<slug>.json (git-ignored).
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from devgrill.domain.spec import SolutionSpec
from devgrill.sandbox.compose import ComposeDriver
from devgrill.sandbox.content import Bundle, ContentError, load_yaml
from devgrill.sandbox.driver import SandboxError, SandboxSpec
from devgrill.sandbox.verifier import ProbeResult, Verifier, check

SLO_BREACH_WITHIN_S = 60
MITIGATION_WITHIN_S = 150
SAMPLE_EVERY_S = 5.0


@dataclass(slots=True)
class Report:
    slug: str
    ok: bool = False
    stage: str = "boot"
    boot_s: float | None = None
    slo_breached_after_s: float | None = None
    symptoms: dict[str, float | None] = field(default_factory=dict)
    mitigated_after_s: float | None = None
    probes: list[dict[str, Any]] = field(default_factory=list)
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

        # ---- break
        report.stage = "break"
        steps = sorted(scenario.faults, key=lambda s: s.at_seconds)
        for step in (s for s in steps if s.at_seconds <= 0):
            await driver.apply_fault(handle, bundle, step.use, dict(step.params))
            echo(f"  applied {step.use} ({step.at})")
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
                echo(f"  applied {step.use} ({step.at})")
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
        echo(f"  SLO breached after {report.slo_breached_after_s}s; symptoms {report.symptoms}")
        if (
            report.slo_breached_after_s is None
            or report.slo_breached_after_s > SLO_BREACH_WITHIN_S
            or pending
        ):
            report.error = "the scenario does not break as declared"
            return report

        # ---- fix
        report.stage = "fix"
        for fix in solution.steps:
            if fix.patch:
                deployed = await driver.patch(
                    handle,
                    bundle,
                    fix.service,
                    (solution_dir / fix.patch).read_bytes(),
                    fix.message,
                )
                if not deployed.ok:
                    report.error = f"solution patch failed: {deployed.message}\n{deployed.log}"
                    return report
            else:
                assert fix.run is not None
                res = await driver.exec(handle, fix.service, ["sh", "-c", fix.run], timeout_s=120)
                if not res.ok:
                    report.error = f"solution command failed: {res.stderr[-1000:]}"
                    return report
            echo(f"  applied solution step: {fix.message}")

        # ---- mitigated: the SLO holds for for_s, within the limit
        report.stage = "mitigate"
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

        # ---- verify
        report.stage = "verify"
        await driver.stop_load(handle)
        results: list[ProbeResult] = await verifier.run_all(scenario.probes)
        report.probes = [asdict(r) for r in results]
        for r in results:
            echo(
                f"  probe {r.key}: {'PASS' if r.passed else 'FAIL'} {r.detail} {_round(r.measured)}"
            )
        if not all(r.passed for r in results):
            report.error = "the reference fix fails probes"
            return report
        report.ok = True
        report.stage = "done"
        return report
    except (SandboxError, ContentError) as exc:
        report.error = f"{report.stage}: {exc}"
        return report
    finally:
        await driver.destroy(handle)


def save_report(content_root: Path, report: Report) -> Path:
    folder = content_root / ".reports"
    folder.mkdir(exist_ok=True)
    path = folder / f"{report.slug}.json"
    path.write_text(json.dumps(asdict(report), indent=2) + "\n", encoding="utf-8", newline="\n")
    return path
