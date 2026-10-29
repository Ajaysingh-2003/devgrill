"""The verifier: attacks a fix from outside the player's reach and decides each probe (ADR 015).

Everything runs in the platform's probe container: k6, scrapes, chaos, SQL through the
read-only role, invariant and hidden tests. Root in the player's shell can change the app and
its data, but not what decides a probe:

- **Trusted measurements only.** Targets use k6's client-side numbers, Postgres's core
  statistics (read with a pinned search_path, reset only by a superuser the player isn't),
  the platform's exporters, and the probe scripts' own output. Metrics the app reports about
  itself are for the charts; `devgrill-content validate` rejects them in probe targets.
- **Honest telemetry is itself checked**: each replay compares what the app's metrics claim
  with what k6 measured (`request_count_drift`, `error_rate_drift`).
- **Fail closed.** A metric that can't be measured fails its target. Chaos is checked after
  it is applied (the flush answered OK, the toxic is still there at the end); statistics
  that went backwards or were reset fail the probe.

Load probes that share a script and multiplier share one replay, so a scenario's probes run in
a few minutes. `plan()` groups them; `run_group()` runs one group (one workflow activity).
"""

from __future__ import annotations

import asyncio
import json
import shlex
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field

from devgrill.domain.enums import ProbeKind
from devgrill.domain.spec import ProbeSpec, ProbeTarget
from devgrill.sandbox.compose import ComposeDriver
from devgrill.sandbox.content import Bundle
from devgrill.sandbox.driver import ExecResult, SandboxError, SandboxHandle
from devgrill.sandbox.metrics import Scrape, evaluate_all, parse_text

REPLAY_SECONDS = 45
CHAOS_WARMUP_S = 10
CHAOS_WINDOW_S = 30
#: A hold_sql step's session name, so it can be ended when the window closes.
HOLD_APP_NAME = "devgrill-chaos"
#: Time a hold_sql step gets to take its locks.
HOLD_START_S = 1.0
_RELEASE_HOLDS_SQL = (
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
    " WHERE application_name = 'devgrill-chaos' AND pid <> pg_backend_pid()"
)
#: Backends flush their statistics at most once a second: wait that long before reading them.
STATS_SETTLE_S = 1.5
SAMPLE_EVERY_S = 2.0
#: How often a replay samples the patchable services' memory (leak checks).
MEMORY_SAMPLE_S = 5.0


# One round trip: every scan of every user table, and when statistics were last reset. The
# catalog is named explicitly: nothing the app role creates can stand in for it.
_DB_STATS_SQL = """
SELECT json_build_object(
  'scans', (SELECT coalesce(sum(seq_scan + coalesce(idx_scan, 0)), 0)
            FROM pg_catalog.pg_stat_user_tables),
  'seq_rows', (SELECT coalesce(sum(seq_tup_read), 0) FROM pg_catalog.pg_stat_user_tables),
  'reset', (SELECT stats_reset FROM pg_catalog.pg_stat_database
            WHERE datname = pg_catalog.current_database())
)::text
"""

Progress = Callable[[str, str], Awaitable[None]]


async def _no_progress(key: str, status: str) -> None:
    return None


@dataclass(slots=True)
class ProbeResult:
    key: str
    kind: str
    title: str
    passed: bool
    weight: float
    measured: dict[str, float | None] = field(default_factory=dict)
    detail: str = ""
    seconds: float = 0.0


def check(targets: Mapping[str, ProbeTarget], measured: Mapping[str, float | None]) -> list[str]:
    """Failed targets as readable lines; an unmeasurable metric counts as failed."""
    failures = []
    for metric, target in targets.items():
        value = measured.get(metric)
        if value is None:
            failures.append(f"{metric}: not measured")
        elif not target.holds(value):
            bound = " and ".join(
                f"{op} {limit:g}"
                for op, limit in (("<", target.lt), (">", target.gt))
                if limit is not None
            )
            failures.append(f"{metric} = {value:.4g}, wanted {bound}")
    return failures


def trusted_metrics(bundle: Bundle) -> frozenset[str]:
    """Base-app metrics measured by the platform, not reported by code the player can edit."""
    app = bundle.base_app
    patchable = set(app.patchable_services)
    return frozenset(name for name, m in app.metrics.items() if m.job not in patchable)


def plan(probes: list[ProbeSpec]) -> list[list[ProbeSpec]]:
    """Probes in run order, load probes that can share a replay grouped (spec order kept)."""
    groups: list[list[ProbeSpec]] = []
    replays: dict[tuple[str | None, float], list[ProbeSpec]] = {}
    for probe in probes:
        if probe.kind is ProbeKind.LOAD:
            key = (probe.script, probe.multiplier)
            if key in replays:
                replays[key].append(probe)
                continue
            replays[key] = [probe]
            groups.append(replays[key])
        else:
            groups.append([probe])
    return groups


class Verifier:
    def __init__(self, driver: ComposeDriver, handle: SandboxHandle, bundle: Bundle) -> None:
        self.driver = driver
        self.handle = handle
        self.bundle = bundle
        self._trusted = trusted_metrics(bundle)

    # ------------------------------------------------------------------- measurements

    async def scrape(self) -> Scrape:
        snapshot = await self.driver.metrics(self.handle, self.bundle)
        return Scrape(
            time.monotonic(), {job: parse_text(text) for job, text in snapshot.raw.items()}
        )

    def values(self, prev: Scrape | None, cur: Scrape) -> dict[str, float | None]:
        """Every base-app metric over a window (the app's own included: charts, drift)."""
        return evaluate_all(self.bundle.base_app.metrics, prev, cur)

    def trusted(self, values: Mapping[str, float | None]) -> dict[str, float | None]:
        return {k: v for k, v in values.items() if k in self._trusted}

    async def db_stats(self) -> tuple[float, str | None, float] | None:
        """(total table scans, last stats reset) through the read-only role; None if no DB."""
        dsn = self.bundle.base_app.readonly_dsn()
        if dsn is None:
            return None
        res = await self.driver.probe(self.handle, ["dg-sql", dsn, _DB_STATS_SQL], timeout_s=20)
        try:
            out = json.loads(res.stdout)
            data = json.loads(out["rows"][0][0])
            return float(data["scans"]), data.get("reset"), float(data.get("seq_rows", 0))
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise SandboxError(f"database statistics unreadable: {res.stdout[:300]}") from exc

    def _k6_command(
        self, *, vus: int, duration_s: int, out: str, script: str | None, csv: str | None = None
    ) -> str:
        profile = self.bundle.scenario.load
        env = {
            "TARGET": self.bundle.base_app.load.target,
            "VUS": str(vus),
            "DURATION": f"{duration_s}s",
            **({k: str(v) for k, v in profile.params.items()} if profile else {}),
        }
        flags = " ".join(f"-e {k}={shlex.quote(v)}" for k, v in env.items())
        if csv:
            flags += f" --out csv={shlex.quote(csv)}"
        default = (
            profile.script if profile else self.bundle.base_app.load.script.removeprefix("load/")
        )
        path = f"/probe/verify/{script}" if script else f"/probe/load/{default}"
        return f"k6 run --quiet {flags} {shlex.quote(path)} > {out} 2>{out}.err"

    def _vus(self, probe: ProbeSpec) -> int:
        base = self.bundle.scenario.load.vus if self.bundle.scenario.load else 20
        return max(1, round(base * probe.multiplier))

    async def _summary(self, out: str) -> dict[str, float | None]:
        result = await self.driver.probe(self.handle, ["sh", "-c", f"cat {out}"])
        for line in reversed(result.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                data = json.loads(line)
                return {
                    k: (
                        float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None
                    )
                    for k, v in data.items()
                }
        err = await self.driver.probe(self.handle, ["sh", "-c", f"tail -c 1500 {out}.err"])
        raise SandboxError(f"k6 produced no summary: {err.stdout}")

    # ------------------------------------------------------------------------- probes

    async def run_all(
        self, probes: list[ProbeSpec], progress: Progress = _no_progress
    ) -> list[ProbeResult]:
        """Every probe, one group at a time (they share the app), results in spec order."""
        by_key: dict[str, ProbeResult] = {}
        for group in plan(probes):
            for result in await self.run_group(group, progress):
                by_key[result.key] = result
        return [by_key[p.key] for p in probes]

    async def run_group(
        self, group: list[ProbeSpec], progress: Progress = _no_progress
    ) -> list[ProbeResult]:
        results = [ProbeResult(p.key, p.kind.value, p.title, False, p.weight) for p in group]
        for r in results:
            await progress(r.key, "running")
        started = time.monotonic()
        try:
            match group[0].kind:
                case ProbeKind.LOAD:
                    measured = await self._replay(group[0])
                    for probe, result in zip(group, results, strict=True):
                        self._judge(probe, result, measured)
                case ProbeKind.CHAOS:
                    self._judge(group[0], results[0], await self._chaos(group[0]))
                case ProbeKind.INVARIANT:
                    await self._script(group[0], results[0], exit_code_decides=False)
                case ProbeKind.HIDDEN_TEST:
                    await self._script(group[0], results[0], exit_code_decides=True)
                case ProbeKind.BUDGET:
                    await self._budget(results[0])
        except SandboxError as exc:
            for r in results:
                r.passed, r.detail = False, str(exc)[-1500:]
        seconds = round(time.monotonic() - started, 1)
        for r in results:
            r.seconds = seconds
            await progress(r.key, "passed" if r.passed else "failed")
        return results

    async def run(self, probe: ProbeSpec) -> ProbeResult:
        return (await self.run_group([probe]))[0]

    async def _replay(self, probe: ProbeSpec) -> dict[str, float | None]:
        """One replay: k6's numbers, the database's work, platform metrics, metric drift."""
        out = f"/probe/out/{probe.key}.json"
        before_db = await self.db_stats()
        before = await self.scrape()
        replay = asyncio.create_task(
            self.driver.probe(
                self.handle,
                [
                    "sh",
                    "-c",
                    self._k6_command(
                        vus=self._vus(probe),
                        duration_s=REPLAY_SECONDS,
                        out=out,
                        script=probe.script,
                    ),
                ],
                timeout_s=REPLAY_SECONDS + 60,
            )
        )  # k6 exits non-zero when its own thresholds fail; the targets decide here
        growth = await self._memory_growth_while(replay)
        after = await self.scrape()
        await asyncio.sleep(STATS_SETTLE_S)
        after_db = await self.db_stats()
        k6 = await self._summary(out)
        app = self.values(before, after)
        measured: dict[str, float | None] = {**self.trusted(app), **k6}
        requests = k6.get("requests") or 0.0
        if before_db is not None and after_db is not None:
            if after_db[1] != before_db[1] or after_db[0] < before_db[0]:
                raise SandboxError("database statistics were reset during the replay")
            scans = after_db[0] - before_db[0]
            measured["db_scans_per_s"] = round(scans / REPLAY_SECONDS, 2)
            measured["db_scans_per_request"] = round(scans / requests, 4) if requests else None
            # Rows read by sequential scans: a missing or unusable index shows here at once.
            seq_rows = after_db[2] - before_db[2]
            measured["db_seq_rows_per_request"] = (
                round(seq_rows / requests, 1) if requests else None
            )
        measured.update(self._drift(app, k6, after.t - before.t))
        measured["app_memory_growth_mb"] = growth
        return measured

    async def _memory_growth_while(self, replay: asyncio.Task[ExecResult]) -> float | None:
        """Memory the player's services gained while `replay` runs: the sum of every rise
        between samples, so a leak still shows when a crash resets memory part way."""
        services = self.bundle.base_app.patchable_services
        last: dict[str, int] = {}
        gained = 0
        try:
            while True:
                for service in services:
                    now = (await self.driver.usage(self.handle, service)).memory_bytes
                    if service in last and now > last[service]:
                        gained += now - last[service]
                    last[service] = now
                done, _ = await asyncio.wait({replay}, timeout=MEMORY_SAMPLE_S)
                if done:
                    break
        finally:
            await replay
        return round(gained / 1_048_576, 1) if services else None

    @staticmethod
    def _drift(
        app: Mapping[str, float | None], k6: Mapping[str, float | None], window_s: float
    ) -> dict[str, float | None]:
        """How far the app's own telemetry is from what k6 measured (honest-metrics probes)."""
        k6_requests, app_rate = k6.get("requests"), app.get("request_rate")
        out: dict[str, float | None] = {"request_count_drift": None, "error_rate_drift": None}
        if k6_requests and app_rate is not None:
            out["request_count_drift"] = round(
                abs(app_rate * window_s - k6_requests) / k6_requests, 4
            )
        k6_errors, app_errors = k6.get("error_rate"), app.get("error_rate")
        if k6_errors is not None and app_errors is not None:
            out["error_rate_drift"] = round(abs(app_errors - k6_errors), 4)
        return out

    async def _chaos(self, probe: ProbeSpec) -> dict[str, float | None]:
        out, csv = f"/probe/out/{probe.key}.json", f"/probe/out/{probe.key}.csv"
        duration = CHAOS_WARMUP_S + CHAOS_WINDOW_S
        command = self._k6_command(
            vus=self._vus(probe), duration_s=duration, out=out, script=probe.script, csv=csv
        )
        replay = asyncio.create_task(
            self.driver.probe(self.handle, ["sh", "-c", command], timeout_s=duration + 60)
        )
        toxics: list[tuple[str, str]] = []
        holds: list[asyncio.Task[ExecResult]] = []
        try:
            await asyncio.sleep(CHAOS_WARMUP_S)
            toxics, holds = await self._chaos_steps(probe)
            clock = await self.driver.probe(self.handle, ["date", "+%s.%N"])
            chaos_at = float(clock.stdout.strip())
            await asyncio.sleep(CHAOS_WINDOW_S - SAMPLE_EVERY_S)
            for proxy, name in toxics:  # still in place at the end, or it was tampered with
                if not await self.driver.toxic_exists(self.handle, self.bundle, proxy, name):
                    raise SandboxError(f"the chaos toxic on {proxy} was removed during the check")
        finally:
            if holds:
                await self._release_holds(holds)
            await replay
            for proxy, name in toxics:
                await self.driver.toxic_delete(self.handle, self.bundle, proxy, name)
        slo = self.bundle.scenario.slo
        p99 = slo.p99_latency_ms if slo and slo.p99_latency_ms else 500.0
        errors = slo.error_rate if slo and slo.error_rate is not None else 0.01
        res = await self.driver.probe(
            self.handle, ["dg-recovery", csv, f"{chaos_at:.3f}", f"{p99:g}", f"{errors:g}"]
        )
        try:
            recovery = json.loads(res.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            raise SandboxError(f"recovery analysis failed: {res.stderr[-500:]}") from exc
        await self.driver.probe(self.handle, ["rm", "-f", csv])
        return {
            **await self._summary(out),
            **{k: (float(v) if v is not None else None) for k, v in recovery.items()},
        }

    async def _chaos_steps(
        self, probe: ProbeSpec
    ) -> tuple[list[tuple[str, str]], list[asyncio.Task[ExecResult]]]:
        app = self.bundle.base_app
        toxics: list[tuple[str, str]] = []
        holds: list[asyncio.Task[ExecResult]] = []
        for index, step in enumerate(probe.steps):
            if step.del_key or step.flush_cache:
                cache = app.cache_service
                if cache is None:
                    raise SandboxError(f"{app.slug} has no cache for {probe.key}")
                argv = [
                    "redis-cli",
                    "-h",
                    cache,
                    *(["DEL", step.del_key] if step.del_key else ["FLUSHALL"]),
                ]
                res = await self.driver.probe(self.handle, argv)
                answer = res.stdout.strip()
                # redis-cli exits 0 on error replies; the answer says whether it happened.
                ok = (
                    answer == "OK"
                    if step.flush_cache
                    else answer.removeprefix("(integer) ").isdigit()
                )
                if not res.ok or not ok:
                    raise SandboxError(f"chaos step refused by the cache: {answer or res.stderr}")
            elif step.restart:
                await self.driver.restart(self.handle, step.restart)
            elif step.toxic:
                name = f"dg-chaos-{probe.key}-{index}"
                await self.driver.toxic(self.handle, self.bundle, name, dict(step.toxic))
                toxics.append((str(step.toxic["proxy"]), name))
            elif step.hold_sql:
                holds.append(await self._hold_sql(step.hold_sql))
        return toxics, holds

    def _psql(self, sql: str) -> tuple[str, list[str]]:
        app = self.bundle.base_app
        service = app.sql_service
        if service is None:
            raise SandboxError(f"{app.slug} has no database for a hold_sql step")
        spec = app.services[service].sql
        assert spec is not None
        argv = ["env", f"PGAPPNAME={HOLD_APP_NAME}", "psql", "-U", spec.user, "-d", spec.database]
        return service, [*argv, "-v", "ON_ERROR_STOP=1", "-c", sql]

    async def _hold_sql(self, sql: str) -> asyncio.Task[ExecResult]:
        """Start `sql` in its own session and leave it running (it ends with the window)."""
        service, argv = self._psql(sql)
        task = asyncio.create_task(
            self.driver.exec(
                self.handle, service, argv, timeout_s=CHAOS_WARMUP_S + CHAOS_WINDOW_S + 60
            )
        )
        await asyncio.sleep(HOLD_START_S)  # let it take its locks before measuring
        if task.done():
            res = task.result()
            raise SandboxError(
                f"the hold_sql step ended early: {(res.stderr or res.stdout)[-300:]}"
            )
        return task

    async def _release_holds(self, holds: list[asyncio.Task[ExecResult]]) -> None:
        service, argv = self._psql(_RELEASE_HOLDS_SQL)
        await self.driver.exec(self.handle, service, argv, timeout_s=30)
        for task in holds:
            try:
                await asyncio.wait_for(task, timeout=30)
            except TimeoutError, SandboxError:
                task.cancel()

    async def _script(
        self, probe: ProbeSpec, result: ProbeResult, *, exit_code_decides: bool
    ) -> None:
        """Invariants and hidden tests: a script in the probe container prints one JSON line."""
        assert probe.script
        app = self.bundle.base_app
        env = {"TARGET": app.load.target}
        if app.cache_service:
            env["CACHE_HOST"] = app.cache_service
        if (dsn := app.readonly_dsn()) is not None:
            env["PG_DSN"] = dsn
        exports = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
        runner = "python3" if probe.script.endswith(".py") else "sh"
        res = await self.driver.probe(
            self.handle,
            ["sh", "-c", f"{exports} {runner} /probe/verify/{shlex.quote(probe.script)}"],
            timeout_s=120,
        )
        report: dict[str, object] = {}
        for line in reversed(res.stdout.splitlines()):
            if line.strip().startswith("{"):
                report = json.loads(line)
                break
        measured: dict[str, float | None] = {
            k: float(v)
            for k, v in report.items()
            if isinstance(v, int | float) and not isinstance(v, bool)
        }
        measured.update({k: None for k, v in report.items() if v is None})
        if not res.ok:
            failures = report.get("failures")
            reason = (
                "; ".join(str(f) for f in failures)
                if isinstance(failures, list) and failures
                else (res.stderr or res.stdout)[-800:]
            )
            result.measured, result.detail = measured, f"check failed: {reason}"[:1500]
            return
        if exit_code_decides and not probe.target:
            result.measured, result.passed, result.detail = measured, True, "every check passed"
            return
        self._judge(probe, result, measured)

    async def _budget(self, result: ProbeResult) -> None:
        limit = self.bundle.scenario.constraints.cache_max_memory_mb
        cache = self.bundle.base_app.cache_service
        failures = []
        measured: dict[str, float | None] = {}
        if limit is not None and cache is not None:
            res = await self.driver.probe(
                self.handle, ["redis-cli", "-h", cache, "CONFIG", "GET", "maxmemory"]
            )
            parts = res.stdout.split()
            maxmemory_mb = (
                int(parts[1]) / (1024 * 1024) if len(parts) == 2 and parts[1].isdigit() else None
            )
            measured["cache_max_memory_mb"] = maxmemory_mb
            if maxmemory_mb is None or maxmemory_mb == 0 or maxmemory_mb > limit:
                failures.append(f"cache maxmemory {maxmemory_mb} MB is over the {limit} MB budget")
        result.measured = measured
        result.passed = not failures
        result.detail = "; ".join(failures) or "within budget"

    @staticmethod
    def _judge(probe: ProbeSpec, result: ProbeResult, measured: dict[str, float | None]) -> None:
        failures = check(probe.target, measured)
        result.measured = {k: measured.get(k) for k in probe.target} or measured
        result.passed = not failures
        result.detail = "; ".join(failures) or "all targets met"
