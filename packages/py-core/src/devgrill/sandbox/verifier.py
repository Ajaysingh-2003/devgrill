"""The verifier: measures a sandbox from the outside (the probe container) and runs probes.

Root in the player's shell can't reach any of this: k6, scrapes, chaos and invariant checks
all run in the platform-owned probe container (PLAN §12.3). Phase 3 runs load, chaos,
invariant and budget probes; hidden tests, scoring and the debrief arrive in phase 5.
"""

from __future__ import annotations

import asyncio
import json
import shlex
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

from devgrill.domain.enums import ProbeKind
from devgrill.domain.spec import ProbeSpec, ProbeTarget
from devgrill.sandbox.compose import ComposeDriver
from devgrill.sandbox.content import Bundle
from devgrill.sandbox.driver import SandboxError, SandboxHandle
from devgrill.sandbox.metrics import Scrape, evaluate_all, parse_text

REPLAY_SECONDS = 45
CHAOS_WARMUP_S = 10
CHAOS_WINDOW_S = 30
SAMPLE_EVERY_S = 2.0


@dataclass(slots=True)
class ProbeResult:
    key: str
    kind: str
    title: str
    passed: bool
    weight: float
    measured: dict[str, float | None] = field(default_factory=dict)
    detail: str = ""


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


class Verifier:
    def __init__(self, driver: ComposeDriver, handle: SandboxHandle, bundle: Bundle) -> None:
        self.driver = driver
        self.handle = handle
        self.bundle = bundle

    # ------------------------------------------------------------------- measurements

    async def scrape(self) -> Scrape:
        snapshot = await self.driver.metrics(self.handle, self.bundle)
        return Scrape(
            time.monotonic(), {job: parse_text(text) for job, text in snapshot.raw.items()}
        )

    def values(self, prev: Scrape | None, cur: Scrape) -> dict[str, float | None]:
        return evaluate_all(self.bundle.base_app.metrics, prev, cur)

    def _k6_command(self, *, vus: int, duration_s: int, out: str, script: str | None) -> str:
        profile = self.bundle.scenario.load
        env = {
            "TARGET": self.bundle.base_app.load.target,
            "VUS": str(vus),
            "DURATION": f"{duration_s}s",
            **({k: str(v) for k, v in profile.params.items()} if profile else {}),
        }
        flags = " ".join(f"-e {k}={shlex.quote(v)}" for k, v in env.items())
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

    async def run(self, probe: ProbeSpec) -> ProbeResult:
        runner = {
            ProbeKind.LOAD: self._load,
            ProbeKind.CHAOS: self._chaos,
            ProbeKind.INVARIANT: self._invariant,
            ProbeKind.BUDGET: self._budget,
        }.get(probe.kind)
        result = ProbeResult(probe.key, probe.kind.value, probe.title, False, probe.weight)
        if runner is None:
            result.detail = f"{probe.kind.value} probes run from phase 5"
            return result
        try:
            await runner(probe, result)
        except SandboxError as exc:
            result.passed, result.detail = False, str(exc)[-1500:]
        return result

    async def run_all(self, probes: list[ProbeSpec]) -> list[ProbeResult]:
        return [await self.run(probe) for probe in probes]  # one at a time: they share the app

    async def _load(self, probe: ProbeSpec, result: ProbeResult) -> None:
        out = f"/probe/out/{probe.key}.json"
        before = await self.scrape()
        replay = await self.driver.probe(
            self.handle,
            [
                "sh",
                "-c",
                self._k6_command(
                    vus=self._vus(probe), duration_s=REPLAY_SECONDS, out=out, script=probe.script
                ),
            ],
            timeout_s=REPLAY_SECONDS + 60,
        )
        after = await self.scrape()
        measured = {**self.values(before, after), **await self._summary(out)}
        del replay  # k6 exits non-zero when its own thresholds fail; the targets decide here
        self._judge(probe, result, measured)

    async def _chaos(self, probe: ProbeSpec, result: ProbeResult) -> None:
        out = f"/probe/out/{probe.key}.json"
        duration = CHAOS_WARMUP_S + CHAOS_WINDOW_S
        command = self._k6_command(
            vus=self._vus(probe), duration_s=duration, out=out, script=probe.script
        )
        replay = asyncio.create_task(
            self.driver.probe(self.handle, ["sh", "-c", command], timeout_s=duration + 60)
        )
        try:
            await asyncio.sleep(CHAOS_WARMUP_S)
            chaos_at = await self.scrape()
            toxics = await self._chaos_steps(probe)
            slo = self.bundle.scenario.slo
            recovered_after: float | None = None
            prev = chaos_at
            while time.monotonic() - chaos_at.t < CHAOS_WINDOW_S - SAMPLE_EVERY_S:
                await asyncio.sleep(SAMPLE_EVERY_S)
                cur = await self.scrape()
                if (
                    recovered_after is None
                    and slo is not None
                    and not check(slo.targets(), self.values(prev, cur))
                ):
                    recovered_after = cur.t - chaos_at.t
                prev = cur
            end = await self.scrape()
            for proxy, name in toxics:
                await self.driver.toxic_delete(self.handle, self.bundle, proxy, name)
        finally:
            await replay
        measured = {
            **self.values(chaos_at, end),
            **await self._summary(out),
            "recovery_s": recovered_after,
        }
        self._judge(probe, result, measured)

    async def _chaos_steps(self, probe: ProbeSpec) -> list[tuple[str, str]]:
        app = self.bundle.base_app
        toxics: list[tuple[str, str]] = []
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
                if not res.ok:
                    raise SandboxError(f"chaos step failed: {res.stderr}")
            elif step.restart:
                await self.driver.restart(self.handle, step.restart)
            elif step.toxic:
                name = f"dg-chaos-{probe.key}-{index}"
                await self.driver.toxic(self.handle, self.bundle, name, dict(step.toxic))
                toxics.append((str(step.toxic["proxy"]), name))
        return toxics

    async def _invariant(self, probe: ProbeSpec, result: ProbeResult) -> None:
        assert probe.script
        app = self.bundle.base_app
        env = {"TARGET": app.load.target}
        if app.cache_service:
            env["CACHE_HOST"] = app.cache_service
        sql = next(((n, s.sql) for n, s in app.services.items() if s.sql), None)
        if sql:
            env["PG_DSN"] = f"postgresql://verifier:verifier@{sql[0]}:5432/{sql[1].database}"
        exports = " ".join(f"{k}={shlex.quote(v)}" for k, v in env.items())
        runner = "python3" if probe.script.endswith(".py") else "sh"
        res = await self.driver.probe(
            self.handle,
            ["sh", "-c", f"{exports} {runner} /probe/verify/{shlex.quote(probe.script)}"],
            timeout_s=120,
        )
        measured: dict[str, float | None] = {}
        for line in reversed(res.stdout.splitlines()):
            if line.strip().startswith("{"):
                measured = {
                    k: (float(v) if v is not None else None) for k, v in json.loads(line).items()
                }
                break
        if not res.ok:
            result.measured, result.detail = (
                measured,
                f"check failed: {(res.stderr or res.stdout)[-800:]}",
            )
            return
        self._judge(probe, result, measured)

    async def _budget(self, probe: ProbeSpec, result: ProbeResult) -> None:
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
