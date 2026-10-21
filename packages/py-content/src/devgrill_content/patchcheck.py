"""Check that patches still apply, without Docker: faults to the pristine base app, and a
scenario's solution on top of its faults. Base-app edits can silently break a patch's
context; `devgrill-content validate` runs this so CI catches it, not a player's sandbox.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from devgrill.domain.spec import FaultApply
from devgrill.sandbox.baseapp import BaseAppSpec
from devgrill.sandbox.content import Bundle, Fault, load_fault, render_apply, resolve_params


def _git_apply(repo: Path, diff: Path) -> str | None:
    # git from PATH, like every developer tool here; the argv is fixed, the paths are ours.
    result = subprocess.run(  # noqa: S603
        ["git", "apply", "-p0", "--whitespace=nowarn", str(diff.resolve())],  # noqa: S607
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    return None if result.returncode == 0 else (result.stderr.strip() or "does not apply")


def _set_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in values:
            lines[i] = f"{key}={values[key]}"
            seen.add(key)
    lines += [f"{k}={v}" for k, v in values.items() if k not in seen]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _copy_sources(app: BaseAppSpec, app_dir: Path, into: Path) -> dict[str, Path]:
    repos = {}
    for name, svc in app.services.items():
        if svc.source and svc.build:
            target = into / name
            shutil.copytree(
                app_dir / svc.build, target, ignore=shutil.ignore_patterns("__pycache__")
            )
            repos[name] = target
    return repos


def _apply(app: BaseAppSpec, repos: dict[str, Path], fault: Fault, step: FaultApply) -> str | None:
    if step.patch and step.service:
        return _git_apply(repos[step.service], fault.folder / step.patch)
    if step.env and step.service in repos:
        source = app.services[step.service].source
        if source and source.config_file:
            _set_env(repos[step.service] / source.config_file, dict(step.env))
    return None


def check_fault(content_root: Path, app: BaseAppSpec, app_dir: Path, ref: str) -> list[str]:
    fault = load_fault(content_root, ref)
    if app.slug not in fault.spec.base_apps:
        return []
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        repos = _copy_sources(app, app_dir, Path(tmp))
        params = resolve_params(fault.spec, {})
        for step in (fault.spec.apply, fault.spec.also):
            if step is not None and (err := _apply(app, repos, fault, render_apply(step, params))):
                errors.append(f"fault {ref}: patch does not apply to {app.slug}: {err}")
    return errors


def check_scenario(
    bundle: Bundle,
    solution_dir: Path,
    solution_patches: list[tuple[str, str]],
    *,
    label: str = "solution",
) -> list[str]:
    """Faults in scenario order, then a fix's patches [(service, file)] (solution, approach)."""
    errors = []
    app = bundle.base_app
    with tempfile.TemporaryDirectory() as tmp:
        repos = _copy_sources(app, bundle.base_app_dir, Path(tmp))
        for step in sorted(bundle.scenario.faults, key=lambda s: s.at_seconds):
            fault = bundle.faults[step.use]
            params = resolve_params(fault.spec, dict(step.params))
            for apply in (fault.spec.apply, fault.spec.also):
                if apply is not None and (
                    err := _apply(app, repos, fault, render_apply(apply, params))
                ):
                    errors.append(f"{bundle.scenario.slug}: fault {step.use} does not apply: {err}")
        for service, patch in solution_patches:
            if service not in repos:
                errors.append(
                    f"{bundle.scenario.slug}: {label} patches {service}, which is not patchable"
                )
            elif err := _git_apply(repos[service], solution_dir / patch):
                errors.append(
                    f"{bundle.scenario.slug}: {label} {patch} does not apply after the faults:"
                    f" {err}"
                )
    return errors
