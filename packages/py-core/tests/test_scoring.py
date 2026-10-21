"""Scoring and ratings (ADR 015), property-tested: the gate's monotonicity and bounds."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from devgrill.domain.enums import AttemptMode, AttemptState
from devgrill.domain.glicko2 import Rating, expected_score
from devgrill.domain.ratings import MAX_DELTA, rate_attempt, rated
from devgrill.domain.scoring import (
    HINT_PENALTY,
    MITIGATION_FLOOR,
    ScoreInput,
    Weights,
    mitigation_credit,
    score,
)

unit = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
minutes = st.one_of(st.none(), st.floats(min_value=0.0, max_value=600.0, allow_nan=False))
pars = st.floats(min_value=1.0, max_value=60.0, allow_nan=False)
hints = st.integers(min_value=0, max_value=3)
updates = st.integers(min_value=0, max_value=10)


@st.composite
def weights(draw: st.DrawFn) -> Weights:
    raw = [draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False)) for _ in range(4)]
    if sum(raw) == 0:
        raw = [0.25, 0.25, 0.25, 0.25]
    total = sum(raw)
    return Weights(*(r / total for r in raw))


@st.composite
def inputs(draw: st.DrawFn) -> ScoreInput:
    return ScoreInput(
        weights=draw(weights()),
        par_minutes=draw(pars),
        mitigation_minutes=draw(minutes),
        resolution=draw(unit),
        slo_held_under_verify=draw(st.booleans()),
        hints_used=draw(hints),
        status_updates=draw(updates),
        postmortem=draw(st.one_of(st.none(), unit)),
    )


def _with(inp: ScoreInput, **changes: object) -> ScoreInput:
    fields = {name: getattr(inp, name) for name in inp.__dataclass_fields__}
    return ScoreInput(**{**fields, **changes})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------- score


@given(inputs())
def test_scores_stay_in_bounds(inp: ScoreInput) -> None:
    s = score(inp)
    assert 0.0 <= s.incident <= 1.0
    assert s.total is None or 0.0 <= s.total <= 1.0
    assert (s.total is None) == (inp.postmortem is None)


@given(inputs(), st.floats(min_value=0.0, max_value=600.0, allow_nan=False))
def test_a_slower_mitigation_never_scores_more(inp: ScoreInput, extra: float) -> None:
    if inp.mitigation_minutes is None:
        return
    slower = _with(inp, mitigation_minutes=inp.mitigation_minutes + extra)
    assert score(slower).incident <= score(inp).incident
    assert score(slower).mitigation_time <= score(inp).mitigation_time


@given(inputs())
def test_never_mitigating_scores_no_more_than_mitigating(inp: ScoreInput) -> None:
    assert score(_with(inp, mitigation_minutes=None)).incident <= score(inp).incident


@given(inputs(), st.integers(min_value=1, max_value=3))
def test_hints_never_increase_the_score(inp: ScoreInput, more: int) -> None:
    helped = _with(inp, hints_used=inp.hints_used + more)
    assert score(helped).incident <= score(inp).incident
    if inp.postmortem is not None:
        assert (score(helped).total or 0.0) <= (score(inp).total or 0.0)


@given(inputs(), unit)
def test_more_resolution_never_scores_less(inp: ScoreInput, better: float) -> None:
    higher = _with(inp, resolution=max(inp.resolution, better))
    assert score(higher).incident >= score(inp).incident


def test_mitigation_credit_shape() -> None:
    assert mitigation_credit(None, 10) == 0.0
    assert mitigation_credit(4, 10) == 1.0
    assert mitigation_credit(10, 10) == 1.0
    assert mitigation_credit(20, 10) == pytest.approx(1.0 - 0.5 * (1.0 - MITIGATION_FLOOR))
    assert mitigation_credit(30, 10) == pytest.approx(MITIGATION_FLOOR)
    assert mitigation_credit(500, 10) == pytest.approx(MITIGATION_FLOOR)


def test_mitigation_counts_only_once_verify_measured_the_slo() -> None:
    base = ScoreInput(
        weights=Weights(),
        par_minutes=10,
        mitigation_minutes=3,
        resolution=0.5,
        slo_held_under_verify=False,
    )
    assert score(base).mitigation_time == 0.0
    assert score(_with(base, slo_held_under_verify=True)).mitigation_time == 1.0


def test_a_perfect_incident_and_the_hint_penalty() -> None:
    perfect = ScoreInput(
        weights=Weights(),
        par_minutes=10,
        mitigation_minutes=5,
        resolution=1.0,
        slo_held_under_verify=True,
        status_updates=2,
    )
    s = score(perfect)
    assert (s.incident, s.total, s.resolved) == (1.0, None, True)
    assert score(_with(perfect, hints_used=2)).incident == pytest.approx(1.0 - 2 * HINT_PENALTY)


# -------------------------------------------------------------------------------- ratings

ratings = st.builds(
    Rating,
    rating=st.floats(min_value=600, max_value=2600, allow_nan=False),
    rd=st.floats(min_value=30, max_value=350, allow_nan=False),
    vol=st.floats(min_value=0.03, max_value=0.1, allow_nan=False),
)
modes = st.sampled_from([AttemptMode.ONCALL, AttemptMode.GUIDED, AttemptMode.DAILY])


@given(ratings, ratings, unit, modes)
def test_rating_changes_are_bounded_and_have_the_right_sign(
    player: Rating, scenario: Rating, outcome: float, mode: AttemptMode
) -> None:
    change = rate_attempt(player, scenario, outcome, mode)
    scenario_delta = change.scenario_after.rating - scenario.rating
    assert abs(change.delta) <= MAX_DELTA + 1e-9
    assert abs(scenario_delta) <= MAX_DELTA + 1e-9
    expected = expected_score(player, scenario)
    if outcome > expected + 1e-9:
        assert change.delta >= 0
    elif outcome < expected - 1e-9:
        assert change.delta <= 0
    # Away from the expectation, the scenario moves the other way. (Right at it, each side's
    # expectation uses the other's deviation, so both can move by a hair.)
    if abs(outcome - expected) > 0.02:
        assert change.delta * scenario_delta <= 1e-9


@given(ratings, ratings, unit)
def test_guided_play_gains_at_most_half_and_loses_the_same(
    player: Rating, scenario: Rating, outcome: float
) -> None:
    oncall = rate_attempt(player, scenario, outcome, AttemptMode.ONCALL).delta
    guided = rate_attempt(player, scenario, outcome, AttemptMode.GUIDED).delta
    if oncall > 0:
        assert guided <= oncall / 2 + 1e-9
    else:
        assert guided == pytest.approx(oncall)


@given(ratings, ratings, unit, unit)
def test_a_better_result_never_rates_lower(
    player: Rating, scenario: Rating, a: float, b: float
) -> None:
    low, high = sorted((a, b))
    assert (
        rate_attempt(player, scenario, high, AttemptMode.ONCALL).delta
        >= rate_attempt(player, scenario, low, AttemptMode.ONCALL).delta - 1e-9
    )


def test_which_attempts_are_rated() -> None:
    def r(**kw: object) -> bool:
        args: dict[str, object] = {
            "signed_in": True,
            "mode": AttemptMode.ONCALL,
            "state": AttemptState.RESOLVED,
            "active_seconds": 600.0,
            "verify_runs": 1,
        }
        return rated(**{**args, **kw})  # type: ignore[arg-type]

    assert r()
    assert not r(signed_in=False)
    assert not r(mode=AttemptMode.TUTORIAL)
    assert not r(state=AttemptState.FAILED)  # our side broke, not the player
    assert r(state=AttemptState.EXPIRED, verify_runs=0)  # ran out of time: a loss
    assert not r(state=AttemptState.ABANDONED, verify_runs=0, active_seconds=60)  # wrong scenario
    assert r(state=AttemptState.ABANDONED, verify_runs=0, active_seconds=600)
    assert r(state=AttemptState.ABANDONED, verify_runs=1, active_seconds=60)
