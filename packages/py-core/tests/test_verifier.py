"""The verifier's tamper checks and judgements (ADR 015), with a fake driver: no Docker.

The end-to-end red team (fake fixes, tampering inside a real sandbox) runs as cheats in
`devgrill-content test --approaches`; these cover the verifier's own refusals precisely.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from devgrill.domain.enums import ProbeKind
from devgrill.domain.spec import ProbeSpec, ProbeTarget
from devgrill.sandbox import verifier as verifier_module
from devgrill.sandbox.content import ContentError, load_bundle
from devgrill.sandbox.driver import ExecResult, MetricSnapshot, ResourceUsage, SandboxHandle
from devgrill.sandbox.verifier import Verifier, check, plan

CONTENT = Path(__file__).resolve().parents[3] / "content"
HANDLE = SandboxHandle("a", "dg-test")


class FakeDriver:
    """Answers the probe container's commands from a script of canned replies."""

    def __init__(
        self,
        *,
        stats: list[tuple[float, str | None]] | None = None,
        k6: dict[str, Any] | None = None,
        redis: str = "OK",
        toxic_there: bool = True,
        script: tuple[int, dict[str, Any]] = (0, {}),
        recovery: dict[str, Any] | None = None,
    ) -> None:
        self.stats = list(stats or [(100.0, "t0"), (1000.0, "t0")])
        self.k6 = k6 or {"p99_ms": 120.0, "error_rate": 0.0, "requests": 1800}
        self.redis = redis
        self.toxic_there = toxic_there
        self.script = script
        self.recovery = recovery or {"recovery_s": 6.0, "after_p99_ms": 90.0, "after_error_rate": 0}
        self.toxics: list[str] = []
        self.deleted: list[str] = []
        self.execs: list[tuple[str, list[str]]] = []
        #: The app's memory, one sample per call (the last one repeats).
        self.memory = [200 * 1_048_576]
        self.replay_s = 0.0
        self.released = asyncio.Event()
        self.hold_fails = False

    async def metrics(self, handle: SandboxHandle, bundle: Any) -> MetricSnapshot:
        return MetricSnapshot(datetime.now(UTC), {})

    async def probe(
        self, handle: SandboxHandle, argv: list[str], *, timeout_s: int = 60
    ) -> ExecResult:
        cmd = argv[0]
        if cmd == "dg-sql":
            scans, reset = self.stats.pop(0)
            row = json.dumps({"scans": scans, "reset": reset})
            return ExecResult(0, json.dumps({"columns": ["x"], "rows": [[row]]}), "")
        if cmd == "redis-cli":
            return ExecResult(0, self.redis + "\n", "")
        if cmd == "date":
            return ExecResult(0, "1000.000\n", "")
        if cmd == "dg-recovery":
            return ExecResult(0, json.dumps(self.recovery) + "\n", "")
        if cmd == "sh" and argv[2].startswith("cat "):
            return ExecResult(0, json.dumps(self.k6) + "\n", "")
        if cmd == "sh" and ("python3" in argv[2] or argv[2].lstrip().startswith("TARGET")):
            code, report = self.script
            return ExecResult(code, json.dumps(report) + "\n", "")
        if cmd == "sh" and "k6 run" in argv[2]:
            await asyncio.sleep(self.replay_s)
        return ExecResult(0, "", "")  # k6 runs, rm, ...

    async def toxic(
        self, handle: SandboxHandle, bundle: Any, name: str, toxic: dict[str, object]
    ) -> None:
        self.toxics.append(name)

    async def toxic_exists(self, handle: SandboxHandle, bundle: Any, proxy: str, name: str) -> bool:
        return self.toxic_there

    async def toxic_delete(self, handle: SandboxHandle, bundle: Any, proxy: str, name: str) -> None:
        self.deleted.append(name)

    async def restart(self, handle: SandboxHandle, service: str) -> None:
        return None

    async def usage(self, handle: SandboxHandle, service: str | None = None) -> ResourceUsage:
        self.memory = self.memory[1:] or self.memory
        return ResourceUsage(cpu_seconds=0.0, memory_bytes=self.memory[0])

    async def exec(
        self, handle: SandboxHandle, service: str, argv: list[str], *, timeout_s: int = 60
    ) -> ExecResult:
        self.execs.append((service, argv))
        sql = argv[-1]
        if "pg_terminate_backend" in sql:
            self.released.set()
            return ExecResult(0, "", "")
        if self.hold_fails:
            return ExecResult(3, "", 'ERROR:  relation "nope" does not exist')
        await self.released.wait()  # a held session runs until it is ended
        return ExecResult(2, "", "FATAL:  terminating connection due to administrator command")


@pytest.fixture(autouse=True)
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verifier_module, "STATS_SETTLE_S", 0)
    monkeypatch.setattr(verifier_module, "CHAOS_WARMUP_S", 0)
    monkeypatch.setattr(verifier_module, "CHAOS_WINDOW_S", verifier_module.SAMPLE_EVERY_S)


def verifier(driver: FakeDriver, slug: str = "big-sale-meltdown") -> Verifier:
    return Verifier(driver, HANDLE, load_bundle(CONTENT, slug))  # type: ignore[arg-type]


def probe(bundle_slug: str, key: str) -> ProbeSpec:
    return next(p for p in load_bundle(CONTENT, bundle_slug).scenario.probes if p.key == key)


# ------------------------------------------------------------------------------- planning


def test_load_probes_sharing_a_replay_run_together() -> None:
    probes = load_bundle(CONTENT, "big-sale-meltdown").scenario.probes
    groups = [[p.key for p in g] for g in plan(list(probes))]
    assert groups[0] == ["sale-replay", "cache-serves-reads", "honest-metrics"]
    assert ["cold-cache"] in groups and ["correctness"] in groups
    assert sum(len(g) for g in groups) == len(probes)


def test_an_unmeasurable_metric_fails_its_target() -> None:
    assert check({"p99_ms": ProbeTarget(lt=500)}, {}) == ["p99_ms: not measured"]
    assert check({"p99_ms": ProbeTarget(lt=500)}, {"p99_ms": None}) == ["p99_ms: not measured"]


def test_app_reported_metrics_are_refused_in_probe_targets(tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "content"
    shutil.copytree(CONTENT, root)
    path = root / "scenarios/caching/ttl-zero/scenario.yaml"
    text = path.read_text(encoding="utf-8").replace(
        "db_scans_per_request: { lt: 1.0 }", "cache_hit_rate: { gt: 0.6 }"
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ContentError, match="reported by the app the player edits"):
        load_bundle(root, "ttl-zero")


# -------------------------------------------------------------------------------- replays


async def test_database_work_is_measured_from_postgres() -> None:
    driver = FakeDriver(
        stats=[(100.0, "t0"), (1000.0, "t0")], k6={"p99_ms": 100.0, "requests": 1800}
    )
    [result] = await verifier(driver).run_group([probe("big-sale-meltdown", "cache-serves-reads")])
    assert result.measured == {"db_scans_per_request": 0.5}
    assert result.passed


async def test_statistics_reset_during_a_replay_fail_the_probe() -> None:
    driver = FakeDriver(stats=[(5000.0, "t0"), (10.0, "t1")])
    [result] = await verifier(driver).run_group([probe("big-sale-meltdown", "cache-serves-reads")])
    assert not result.passed
    assert "reset during the replay" in result.detail


# ---------------------------------------------------------------------------------- chaos


async def test_a_refused_flush_fails_the_chaos_probe() -> None:
    driver = FakeDriver(redis="(error) NOPERM this user has no permissions to run 'flushall'")
    [result] = await verifier(driver).run_group([probe("big-sale-meltdown", "cold-cache")])
    assert not result.passed
    assert "refused by the cache" in result.detail


async def test_a_removed_toxic_fails_the_chaos_probe() -> None:
    chaos = ProbeSpec.model_validate(
        {
            "key": "slow-db",
            "kind": ProbeKind.CHAOS,
            "title": "Slow database",
            "how": "Adds 200 ms to every query.",
            "steps": [{"toxic": {"proxy": "postgres", "type": "latency", "latency": 200}}],
            "target": {"recovery_s": {"lt": 30}},
        }
    )
    driver = FakeDriver(toxic_there=False)
    [result] = await verifier(driver).run_group([chaos])
    assert not result.passed
    assert "removed during the check" in result.detail
    assert driver.deleted == driver.toxics  # cleaned up even when the check fails


async def test_a_leak_shows_as_memory_growth_even_across_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verifier_module, "MEMORY_SAMPLE_S", 0.001)
    mb = 1_048_576
    driver = FakeDriver()
    # Grows 100 MB, is OOM-killed back to 150, grows another 120: 220 MB gained.
    driver.memory = [200 * mb, 200 * mb, 250 * mb, 300 * mb, 150 * mb, 270 * mb]
    driver.replay_s = 0.05
    measured = await verifier(driver, "pool-party")._replay(probe("pool-party", "steady-traffic"))
    assert measured["app_memory_growth_mb"] == 220.0


def _hold_probe() -> ProbeSpec:
    return ProbeSpec.model_validate(
        {
            "key": "lock-guard",
            "kind": ProbeKind.CHAOS,
            "title": "A migration stalls again",
            "how": "Holds a lock on orders; product pages stay up.",
            "steps": [{"hold_sql": "BEGIN; LOCK TABLE orders; SELECT pg_sleep(600);"}],
            "target": {"product_p99_ms": {"lt": 500}, "product_error_rate": {"lt": 0.01}},
        }
    )


async def test_held_sql_runs_as_the_app_and_is_ended_after_the_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verifier_module, "HOLD_START_S", 0.01)
    driver = FakeDriver(
        k6={"p99_ms": 900.0, "error_rate": 0.04, "product_p99_ms": 80.0, "product_error_rate": 0}
    )
    [result] = await verifier(driver, "pool-party").run_group([_hold_probe()])
    assert result.passed, result.detail
    (service, held), (_, release) = driver.execs
    assert service == "postgres-db"
    assert held[:2] == ["env", "PGAPPNAME=devgrill-chaos"] and "-U" in held and "shopkart" in held
    assert held[-1].startswith("BEGIN; LOCK TABLE orders")
    assert "application_name = 'devgrill-chaos'" in release[-1]
    # Product pages measured by k6 decide it, whatever the rest of the traffic did.
    assert result.measured == {"product_p99_ms": 80.0, "product_error_rate": 0.0}


async def test_a_hold_that_ends_early_fails_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verifier_module, "HOLD_START_S", 0.01)
    driver = FakeDriver()
    driver.hold_fails = True
    [result] = await verifier(driver, "pool-party").run_group([_hold_probe()])
    assert not result.passed
    assert "ended early" in result.detail and "does not exist" in result.detail


async def test_recovery_comes_from_k6s_own_results() -> None:
    driver = FakeDriver(
        recovery={"recovery_s": 45.0, "after_p99_ms": 900.0, "after_error_rate": 0.2}
    )
    [result] = await verifier(driver).run_group([probe("big-sale-meltdown", "cold-cache")])
    assert not result.passed
    assert result.measured == {"recovery_s": 45.0}


# ----------------------------------------------------------------------------- hidden tests


async def test_a_hidden_test_is_decided_by_its_exit_code() -> None:
    failing = FakeDriver(
        script=(1, {"checks": 15, "checks_failed": 1, "failures": ["product 1042: got 503"]})
    )
    [result] = await verifier(failing).run_group([probe("big-sale-meltdown", "correctness")])
    assert not result.passed
    assert "product 1042: got 503" in result.detail

    passing = FakeDriver(script=(0, {"checks": 15, "checks_failed": 0, "failures": []}))
    [result] = await verifier(passing).run_group([probe("big-sale-meltdown", "correctness")])
    assert result.passed and result.measured["checks"] == 15.0
