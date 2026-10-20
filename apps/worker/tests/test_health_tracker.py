"""Mitigation detection: breached, then healthy for long enough; regression after that."""

from devgrill_worker.sandbox_activities import HealthTracker


def feed(
    tracker: HealthTracker, samples: list[tuple[float, bool | None]]
) -> list[tuple[float, bool]]:
    changes = []
    for t, healthy in samples:
        change = tracker.observe(healthy, t)
        if change is not None:
            changes.append((t, change))
    return changes


def every(
    start: float, end: float, healthy: bool | None, step: float = 2
) -> list[tuple[float, bool | None]]:
    out, t = [], start
    while t < end:
        out.append((t, healthy))
        t += step
    return out


def test_healthy_from_the_start_is_not_mitigation() -> None:
    # Before the fault bites, the SLO holds: that is not the player's doing.
    assert feed(HealthTracker(hold_s=30), every(0, 120, True)) == []


def test_breach_then_hold_is_mitigation() -> None:
    samples = every(0, 20, False) + every(20, 80, True)
    assert feed(HealthTracker(hold_s=30), samples) == [(50, True)]


def test_a_blip_restarts_the_hold() -> None:
    samples = every(0, 10, False) + every(10, 30, True) + [(30, False)] + every(32, 80, True)
    assert feed(HealthTracker(hold_s=30), samples) == [(62, True)]


def test_regression_after_mitigation() -> None:
    samples = every(0, 10, False) + every(10, 50, True) + every(50, 90, False)
    assert feed(HealthTracker(hold_s=30, regress_s=20), samples) == [(40, True), (70, False)]


def test_unknown_samples_change_nothing() -> None:
    samples = every(0, 10, False) + every(10, 100, None) + every(100, 140, True)
    assert feed(HealthTracker(hold_s=30), samples) == [(130, True)]
