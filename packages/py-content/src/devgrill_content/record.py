"""`devgrill-content record <slug>`: capture a case file's evidence from a real run (ADR 018).

The run is the reference test's first half, so a recording is only ever of an incident that
really breaks and stays broken:
  boot → faults → load → BREAKS (the first capture) → left alone → STAYS BROKEN (the second)
Nothing is fixed: the recording ends with the incident still going. It keeps what the
workspace's panels show: the metric series, logs, deploy history with each diff, the source,
Postgres and cache insights, the state of each service, and the commands in `case.yaml`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from devgrill.domain.casefile import missing_clues
from devgrill.domain.spec import (
    CaseCapture,
    CaseCommand,
    CaseEvidence,
    CaseFileSpec,
    CaseLogLine,
    CaseSample,
)
from devgrill.sandbox.compose import ComposeDriver
from devgrill.sandbox.content import (
    Bundle,
    ContentError,
    evidence_path,
    load_bundle,
    load_case_spec,
    load_evidence,
)
from devgrill.sandbox.driver import SandboxError, SandboxHandle, SandboxSpec
from devgrill.sandbox.verifier import Verifier, check
from devgrill_content.scenario_test import SAMPLE_EVERY_S, Report, _break, _round, _stays_broken

#: Log lines kept per service at each of the two captures.
LOG_TAIL = 200
LOG_LINE_CHARS = 400
MAX_DIFF_CHARS = 16_000
MAX_FILE_BYTES = 48_000
MAX_OUTPUT_CHARS = 8_000
SKIP_FILES = (".lock", ".png", ".jpg", ".ico")
SNAPSHOT_TRIES = 3
#: "Still going" is judged on the last few samples: one good one can be noise.
STILL_BROKEN_SAMPLES = 3


def source_hash(bundle: Bundle) -> str:
    """What a recording depends on: the scenario, its faults and the base app's version."""
    source = {
        "scenario": bundle.scenario.model_dump(mode="json"),
        "faults": {k: f.spec.model_dump(mode="json") for k, f in sorted(bundle.faults.items())},
        "base_app": bundle.base_app.version,
    }
    return hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()


def is_stale(bundle: Bundle) -> bool:
    """No recording yet, or recorded from an older scenario, fault or base app."""
    try:
        return load_evidence(bundle.scenario_dir).source_hash != source_hash(bundle)
    except ContentError, ValueError:
        return True


def check_case_file(bundle: Bundle) -> tuple[list[str], bool]:
    """(problems, stale): every playable scenario ships a case file whose evidence shows its
    clues. A stale recording is only a note: it was true of the version it was recorded from,
    and re-recording takes a sandbox."""
    try:
        spec = load_case_spec(bundle.scenario_dir)
        evidence = load_evidence(bundle.scenario_dir)
    except (ContentError, ValueError) as exc:
        return [str(exc)], False
    problems = [
        f"the {clue.panel} evidence doesn't contain {clue.contains!r}"
        for clue in missing_clues(spec, evidence)
    ]
    unknown = sorted({c.service for c in spec.captures} - set(bundle.base_app.services))
    problems.extend(f"a capture runs in unknown service {name}" for name in unknown)
    if not still_broken(bundle, evidence.samples):
        problems.append("the recording ends with the incident over: record it again")
    return problems, evidence.source_hash != source_hash(bundle)


def still_broken(bundle: Bundle, samples: list[CaseSample]) -> bool:
    """Does it end with the incident still going? The reference test only asks that the SLO
    doesn't hold for `for_s` within its window, so a break that heals near the end passes that
    and would show the player a queue already empty, or a chart already green."""
    slo = bundle.scenario.slo
    if slo is None:
        return False
    last = samples[-STILL_BROKEN_SAMPLES:]
    broken = sum(bool(check(slo.targets(), s.values)) for s in last)
    return broken * 2 > len(last)


def _clean(text: str, handle: SandboxHandle) -> str:
    """Sandbox names mean nothing to a reader, and differ on every recording."""
    return text.replace(handle.ref, "sandbox").replace(handle.attempt_id, "run")


def _samples(report: Report) -> list[CaseSample]:
    """The break's samples and the unfixed ones, on one clock from the start of the load."""
    samples = []
    offset = 0.0
    last = 0.0
    phase = None
    for raw in report.samples:
        if phase is not None and raw["phase"] != phase:
            offset = last
        phase = raw["phase"]
        t = round(raw["t"] + offset, 1)
        last = t
        values = {k: v for k, v in raw.items() if k not in ("t", "phase")}
        samples.append(CaseSample(t=t, values=values))
    return samples


async def _logs(
    driver: ComposeDriver,
    handle: SandboxHandle,
    t0: float,
    kept: dict[tuple[float, str, str], CaseLogLine],
) -> None:
    async for line in driver.logs(handle, tail=LOG_TAIL):
        at = line.ts.timestamp()
        kept[(at, line.service, line.line)] = CaseLogLine(
            t=round(at - t0, 3),
            service=line.service,
            line=_clean(line.line, handle)[:LOG_LINE_CHARS],
        )


async def _snapshot(fetch: Any, *args: Any) -> dict[str, Any] | None:
    """A panel's snapshot: an overloaded database may need a second ask."""
    for attempt in range(SNAPSHOT_TRIES):
        try:
            data: dict[str, Any] = await fetch(*args)
            return data
        except SandboxError, ValueError:
            if attempt + 1 < SNAPSHOT_TRIES:
                await asyncio.sleep(3)
    return None


async def _command(
    driver: ComposeDriver, handle: SandboxHandle, capture: CaseCapture
) -> CaseCommand:
    result = await driver.exec(handle, capture.service, ["sh", "-c", capture.run], timeout_s=45)
    output = result.stdout + (f"\n{result.stderr}" if result.stderr.strip() else "")
    return CaseCommand(
        title=capture.title,
        service=capture.service,
        command=capture.run,
        output=_clean(output.strip(), handle)[:MAX_OUTPUT_CHARS],
        ok=result.ok,
    )


def _status_command(status: list[dict[str, Any]]) -> CaseCommand:
    """`devgrill status`, as the terminal prints it."""
    lines = [f"{'SERVICE':<22}{'STATE':<12}{'HEALTH':<12}RESTARTS"]
    for s in status:
        oom = "  (out of memory)" if s.get("oom_killed") else ""
        health = s.get("health") or "-"
        lines.append(
            f"{s['name']:<22}{s.get('state') or '-':<12}{health:<12}{s.get('restarts', 0)}{oom}"
        )
    return CaseCommand(
        title="Every service",
        service="tools",
        command="devgrill status",
        output="\n".join(lines),
        ok=True,
    )


async def _source(
    driver: ComposeDriver, handle: SandboxHandle, bundle: Bundle
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, str]]]:
    deploys: dict[str, dict[str, Any]] = {}
    changes: dict[str, dict[str, Any]] = {}
    files: dict[str, dict[str, str]] = {}
    for service in bundle.base_app.patchable_services:
        history = await driver.deploy_history(handle, bundle, service)
        deploys[service] = history
        for commit in history["commits"]:
            change = await driver.commit_changes(handle, bundle, service, commit["sha"])
            if len(change["diff"]) > MAX_DIFF_CHARS:
                change["diff"] = change["diff"][:MAX_DIFF_CHARS] + "\n(cut short in this recording)"
            change["diff"] = _clean(change["diff"], handle)
            changes[commit["sha"]] = change
        kept: dict[str, str] = {}
        for path in await driver.list_files(handle, bundle, service):
            if path.endswith(SKIP_FILES):
                continue
            data = await driver.read_file(handle, bundle, service, path)
            if len(data) <= MAX_FILE_BYTES and b"\0" not in data:
                kept[path] = _clean(data.decode("utf-8", errors="replace"), handle)
        files[service] = kept
    return deploys, changes, files


def _db_rates(
    first: dict[str, Any] | None, last: dict[str, Any] | None, seconds: float
) -> dict[str, float]:
    if not first or not last or seconds <= 0:
        return {}
    before = {t["query"]: t["calls"] for t in first.get("top", [])}
    return {
        t["query"]: round(max(0.0, (t["calls"] - before[t["query"]]) / seconds), 1)
        for t in last.get("top", [])
        if t["query"] in before
    }


async def _hold(verifier: Verifier, report: Report, seconds: int) -> None:
    """Keep sampling, unfixed, for evidence that takes longer to show."""
    started = time.monotonic()
    prev = await verifier.scrape()
    while time.monotonic() - started < seconds:
        await asyncio.sleep(SAMPLE_EVERY_S)
        cur = await verifier.scrape()
        values = verifier.values(prev, cur)
        prev = cur
        elapsed = round(time.monotonic() - started, 1)
        report.samples.append({"t": elapsed, "phase": "hold", **_round(values)})


async def record(
    bundle: Bundle, spec: CaseFileSpec, driver: ComposeDriver, *, echo: Any = print
) -> CaseEvidence:
    report = Report(bundle.scenario.slug)
    handle = await driver.create(SandboxSpec(f"record-{uuid.uuid4()}", bundle))
    verifier = Verifier(driver, handle, bundle)
    has_db = bundle.base_app.readonly_dsn() is not None
    has_cache = bundle.base_app.cache_service is not None
    try:
        if not await _break(bundle, driver, handle, verifier, report):
            raise ContentError(
                f"{bundle.scenario.slug}: it doesn't break as declared"
                f" (breached after {report.slo_breached_after_s}, symptoms {report.symptoms})"
            )
        assert report.load_started_at is not None
        assert report.slo_breached_after_s is not None
        t0 = report.load_started_at
        echo(f"  broke after {report.slo_breached_after_s}s: first capture")
        kept: dict[tuple[float, str, str], CaseLogLine] = {}
        await _logs(driver, handle, t0, kept)
        first_db = await _snapshot(driver.db_insights, handle, bundle) if has_db else None
        first_at = time.monotonic()

        if not await _stays_broken(bundle, verifier, report):
            raise ContentError(f"{bundle.scenario.slug}: it recovered on its own")
        if spec.hold_s:
            await _hold(verifier, report, spec.hold_s)
        samples = _samples(report)
        if not still_broken(bundle, samples):
            raise ContentError(f"{bundle.scenario.slug}: the incident was over by the end")
        echo("  stayed broken: second capture")
        await _logs(driver, handle, t0, kept)
        db = await _snapshot(driver.db_insights, handle, bundle) if has_db else None
        rates = _db_rates(first_db, db, time.monotonic() - first_at)
        cache = await _snapshot(driver.cache_insights, handle, bundle) if has_cache else None
        status = await driver.status(handle)
        commands = [_status_command(status)]
        for capture in spec.captures:
            commands.append(await _command(driver, handle, capture))
            if not commands[-1].ok:
                echo(f"  note: capture {capture.title!r} failed: {commands[-1].output[-200:]}")
        deploys, changes, files = await _source(driver, handle, bundle)
        duration = time.time() - t0
        return CaseEvidence(
            schema="devgrill/case-evidence@1",
            source_hash=source_hash(bundle),
            recorded_at=round(t0, 1),
            duration_s=round(duration, 1),
            breached_after_s=report.slo_breached_after_s,
            samples=samples,
            logs=sorted(kept.values(), key=lambda line: line.t),
            status=status,
            deploys=deploys,
            changes=changes,
            files=files,
            db=db,
            db_rates=rates,
            cache=cache,
            commands=commands,
        )
    finally:
        await driver.destroy(handle)


def save(bundle: Bundle, evidence: CaseEvidence) -> Path:
    path = evidence_path(bundle.scenario_dir)
    data = evidence.model_dump(mode="json", by_alias=True)
    text = json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    path.write_bytes(text.encode("utf-8"))
    return path


async def record_one(root: Path, slug: str, driver: ComposeDriver, *, echo: Any = print) -> Path:
    bundle = load_bundle(root, slug)
    spec = load_case_spec(bundle.scenario_dir)
    started = time.monotonic()
    evidence = await record(bundle, spec, driver, echo=echo)
    path = save(bundle, evidence)
    took = time.monotonic() - started
    echo(f"  {path.as_posix()}: {path.stat().st_size // 1024} KB in {took:.0f}s")
    return path
