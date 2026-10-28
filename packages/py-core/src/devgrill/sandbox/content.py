"""Load a scenario with everything a sandbox needs: its base app and its fault modules.

`load_bundle` does every cross-file check that the per-file Pydantic models can't: the base
app exists, faults exist and target this base app, params are known and typed, referenced
files exist, symptom metrics are defined. `devgrill-content validate` and the driver both
call it, so a broken reference fails before a sandbox boots.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from devgrill.domain.enums import ProbeKind
from devgrill.domain.spec import ApproachSpec, FaultApply, FaultSpec, ScenarioSpec
from devgrill.sandbox.baseapp import BaseAppSpec, load_base_app

_TEMPLATE = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


class ContentError(ValueError):
    """A content file is invalid or refers to something that doesn't exist."""


@dataclass(frozen=True, slots=True)
class Fault:
    ref: str
    folder: Path
    spec: FaultSpec


@dataclass(frozen=True, slots=True)
class Bundle:
    """A scenario and everything it references, loaded and cross-checked."""

    content_root: Path
    scenario_dir: Path
    scenario: ScenarioSpec
    base_app_dir: Path
    base_app: BaseAppSpec
    faults: dict[str, Fault]


def find_scenario(content_root: Path, slug: str) -> Path:
    matches = sorted((content_root / "scenarios").glob(f"*/{slug}/scenario.yaml"))
    if not matches:
        raise ContentError(f"no scenario {slug!r} under {content_root / 'scenarios'}")
    return matches[0].parent


def load_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ContentError(f"{path}: {exc}") from exc


def load_fault(content_root: Path, ref: str) -> Fault:
    folder = content_root / "faults" / ref
    path = folder / "fault.yaml"
    if not path.is_file():
        raise ContentError(f"fault {ref!r} not found ({path})")
    spec = FaultSpec.model_validate(load_yaml(path))
    if spec.name != ref:
        raise ContentError(f"{path}: name {spec.name!r} does not match its folder {ref!r}")
    for step in (spec.apply, spec.also, spec.revert):
        if step is None:
            continue
        for rel in (step.patch, step.script):
            if rel and not (folder / rel).is_file():
                raise ContentError(f"{path}: {rel} is missing")
    return Fault(ref, folder, spec)


def resolve_params(fault: FaultSpec, given: dict[str, object]) -> dict[str, object]:
    """Merge the scenario's params over the fault's defaults, checking names and types."""
    unknown = set(given) - set(fault.params)
    if unknown:
        raise ContentError(f"{fault.name}: unknown params {sorted(unknown)}")
    out: dict[str, object] = {}
    for name, param in fault.params.items():
        value = given.get(name, param.default)
        if value is None:
            raise ContentError(f"{fault.name}: param {name!r} has no value and no default")
        ok = {
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, int | float) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
        }[param.type]
        if not ok:
            raise ContentError(f"{fault.name}: param {name!r} must be {param.type}, got {value!r}")
        out[name] = value
    return out


def render(value: str, params: dict[str, object]) -> str:
    """Substitute {{name}} placeholders. Unknown names are an error, not an empty string."""

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            raise ContentError(f"unknown placeholder {{{{{name}}}}}")
        return str(params[name])

    return _TEMPLATE.sub(sub, value)


def render_apply(step: FaultApply, params: dict[str, object]) -> FaultApply:
    data = step.model_dump()
    if step.env:
        data["env"] = {k: render(v, params) for k, v in step.env.items()}
    if step.toxic:
        data["toxic"] = {
            k: render(v, params) if isinstance(v, str) else v for k, v in step.toxic.items()
        }
    return FaultApply.model_validate(data)


def _check_step(bundle_app: BaseAppSpec, fault: Fault, step: FaultApply) -> None:
    services = bundle_app.services
    if step.service and step.service not in services:
        raise ContentError(f"{fault.ref}: service {step.service!r} is not in {bundle_app.slug}")
    if step.patch and not (step.service and services[step.service].source):
        raise ContentError(f"{fault.ref}: patches need a patchable service (one with `source`)")
    if step.toxic and not bundle_app.toxiproxy_service:
        raise ContentError(f"{fault.ref}: {bundle_app.slug} has no toxiproxy service")
    if (
        step.script
        and step.script.endswith(".sql")
        and not (step.service and services[step.service].sql)
    ):
        raise ContentError(f"{fault.ref}: .sql scripts need a service with `sql`")


def load_bundle(content_root: Path, slug: str) -> Bundle:
    scenario_dir = find_scenario(content_root, slug)
    scenario = ScenarioSpec.model_validate(load_yaml(scenario_dir / "scenario.yaml"))
    if scenario.slug != slug:
        raise ContentError(f"{scenario_dir}: slug {scenario.slug!r} does not match its folder")
    try:
        base_dir, base_app = load_base_app(content_root, scenario.base_app)
    except (OSError, ValueError) as exc:
        raise ContentError(f"{slug}: base app {scenario.base_app!r}: {exc}") from exc

    faults: dict[str, Fault] = {}
    for step in scenario.faults:
        fault = faults.get(step.use) or load_fault(content_root, step.use)
        if base_app.slug not in fault.spec.base_apps:
            raise ContentError(f"{slug}: fault {step.use} is not written for {base_app.slug}")
        params = resolve_params(fault.spec, dict(step.params))
        for apply in (fault.spec.apply, fault.spec.also, fault.spec.revert):
            if apply is not None:
                _check_step(base_app, fault, render_apply(apply, params))
        if fault.spec.symptom.metric not in base_app.metrics:
            raise ContentError(
                f"{step.use}: symptom metric {fault.spec.symptom.metric!r} is not defined by "
                f"{base_app.slug}"
            )
        faults[step.use] = fault

    if scenario.load and not (base_dir / "load" / scenario.load.script).is_file():
        raise ContentError(f"{slug}: load script load/{scenario.load.script} is missing")
    for chart in scenario.charts:
        if chart not in base_app.metrics:
            raise ContentError(f"{slug}: chart {chart!r} is not a {base_app.slug} metric")
    patchable = set(base_app.patchable_services)
    trusted = {name for name, m in base_app.metrics.items() if m.job not in patchable}
    for probe in scenario.probes:
        if probe.script and not probe_script_path(scenario_dir, base_dir, probe.script).exists():
            raise ContentError(f"{slug}: probe {probe.key}: verify/{probe.script} is missing")
        if probe.kind not in (ProbeKind.LOAD, ProbeKind.CHAOS):
            continue  # invariant scripts and hidden tests report their own measurements
        for metric in probe.target:
            if metric in VERIFIER_METRICS or metric in trusted:
                continue
            if metric in base_app.metrics:
                # The app reports it about itself: the player can make it say anything.
                measured = ", ".join(sorted(VERIFIER_METRICS))
                raise ContentError(
                    f"{slug}: probe {probe.key}: {metric!r} is reported by the app the player "
                    f"edits; use a metric the verifier measures ({measured})"
                )
            raise ContentError(f"{slug}: probe {probe.key}: unknown metric {metric!r}")
    return Bundle(content_root, scenario_dir, scenario, base_dir, base_app, faults)


def load_approaches(bundle: Bundle) -> list[tuple[Path, ApproachSpec]]:
    """`approaches/*.yaml` in file-name order (the debrief matches them in this order)."""
    folder = bundle.scenario_dir / "approaches"
    out: list[tuple[Path, ApproachSpec]] = []
    keys: set[str] = set()
    probe_keys = {p.key for p in bundle.scenario.probes}
    for path in sorted(folder.glob("*.yaml")) if folder.is_dir() else []:
        try:
            spec = ApproachSpec.model_validate(load_yaml(path))
        except ValueError as exc:
            raise ContentError(f"{path}: {exc}") from exc
        if spec.key in keys:
            raise ContentError(f"{path}: approach key {spec.key!r} is used twice")
        keys.add(spec.key)
        if unknown := set(spec.fails_probes) - probe_keys:
            raise ContentError(f"{path}: fails_probes names unknown probes {sorted(unknown)}")
        for step in spec.steps:
            if step.service not in bundle.base_app.services:
                raise ContentError(f"{path}: step targets unknown service {step.service!r}")
            if step.patch and not (folder / step.patch).is_file():
                raise ContentError(f"{path}: {step.patch} is missing")
            if step.rollback_to and step.rollback_to not in {
                e.message for e in bundle.scenario.deploy_history
            }:
                raise ContentError(f"{path}: no deploy {step.rollback_to!r} to roll back to")
        out.append((folder, spec))
    return out


def probe_script_path(scenario_dir: Path, base_dir: Path, script: str) -> Path:
    """`base/<file>` is the base app's standard check; anything else is the scenario's own."""
    if script.startswith("base/"):
        return base_dir / "verify" / script.removeprefix("base/")
    return scenario_dir / "verify" / script


#: What the verifier measures itself (ADR 015): k6's client-side numbers, Postgres's core
#: statistics, the app's telemetry checked against k6, and recovery after chaos.
VERIFIER_METRICS = frozenset(
    {
        "p99_ms",
        "p95_ms",
        "error_rate",
        "product_p99_ms",
        "product_error_rate",
        "requests",
        "db_scans_per_s",
        "db_scans_per_request",
        "request_count_drift",
        "error_rate_drift",
        "recovery_s",
        "app_memory_growth_mb",
        "after_p99_ms",
        "after_error_rate",
    }
)
