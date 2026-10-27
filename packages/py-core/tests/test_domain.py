"""Attempt lifecycle, scoring and streak rules."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from devgrill.domain.attempt import (
    LIVE_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    InvalidTransitionError,
    can_transition,
    is_live,
    transition,
)
from devgrill.domain.enums import AttemptState, ProbeKind, StreakMode
from devgrill.domain.scoring import Probe, ProbeOutcome, verify_score
from devgrill.domain.streaks import activity_day, compute_streak

S = AttemptState

# ------------------------------------------------------------------ attempt lifecycle


def test_every_state_has_a_transition_entry() -> None:
    assert set(TRANSITIONS) == set(AttemptState)


def test_live_and_terminal_states_partition_the_lifecycle() -> None:
    assert set(AttemptState) == LIVE_STATES | TERMINAL_STATES
    assert not LIVE_STATES & TERMINAL_STATES


def test_terminal_states_never_move() -> None:
    for state in TERMINAL_STATES:
        assert TRANSITIONS[state] == frozenset()


def test_happy_path() -> None:
    state = S.PROVISIONING
    for target in (S.ACTIVE, S.MITIGATED, S.VERIFYING, S.RESOLVED):
        state = transition(state, target)
    assert state is S.RESOLVED
    assert not is_live(state)


def test_failed_verify_returns_to_investigation() -> None:
    assert can_transition(S.VERIFYING, S.ACTIVE)
    assert can_transition(S.VERIFYING, S.MITIGATED)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.PROVISIONING, S.RESOLVED),  # can't resolve without playing
        (S.ACTIVE, S.RESOLVED),  # resolution only comes from verify
        (S.RESOLVED, S.ACTIVE),
        (S.ABANDONED, S.ACTIVE),
        (S.ACTIVE, S.PROVISIONING),
    ],
)
def test_illegal_moves_raise(current: AttemptState, target: AttemptState) -> None:
    with pytest.raises(InvalidTransitionError) as err:
        transition(current, target)
    assert err.value.current is current
    assert err.value.target is target


@given(st.sampled_from(sorted(LIVE_STATES)))
def test_every_live_state_can_be_abandoned_or_expire(state: AttemptState) -> None:
    # A sandbox must always be reclaimable: every live state can reach a terminal one.
    assert TRANSITIONS[state] & TERMINAL_STATES


# ---------------------------------------------------------------------------- scoring


def _outcome(weight: float, passed: bool) -> ProbeOutcome:
    return ProbeOutcome(Probe(key=f"p{weight}", kind=ProbeKind.LOAD, weight=weight), passed)


def test_verify_score_is_the_weighted_share_of_passes() -> None:
    assert verify_score([_outcome(3, True), _outcome(1, False)]) == pytest.approx(0.75)


def test_no_probes_scores_zero() -> None:
    assert verify_score([]) == 0.0


def test_probe_weights_must_be_positive() -> None:
    with pytest.raises(ValueError):
        Probe(key="x", kind=ProbeKind.LOAD, weight=0)


# ---------------------------------------------------------------------------- streaks

TODAY = date(2026, 10, 13)


def _days(*offsets: int) -> list[date]:
    return [TODAY - timedelta(days=o) for o in offsets]


def test_ist_rollover_puts_late_utc_evenings_on_the_next_day() -> None:
    # 19:00 UTC is 00:30 IST the next day.
    at = datetime(2026, 10, 12, 19, 0, tzinfo=UTC)
    assert activity_day(at) == date(2026, 10, 13)
    assert activity_day(at, "UTC") == date(2026, 10, 12)


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError):
        activity_day(datetime(2026, 10, 13, 12, 0))


def test_streak_counts_consecutive_days() -> None:
    s = compute_streak(_days(0, 1, 2), TODAY)
    assert (s.current, s.longest, s.last_day) == (3, 3, TODAY)


def test_today_in_progress_does_not_break_the_streak() -> None:
    assert compute_streak(_days(1, 2, 3), TODAY).current == 3


def test_a_missed_day_breaks_the_streak() -> None:
    s = compute_streak(_days(0, 2, 3, 4), TODAY)
    assert (s.current, s.longest) == (1, 3)


def test_a_freeze_bridges_one_missed_day() -> None:
    s = compute_streak(_days(0, 2, 3), TODAY, freezes=1)
    assert (s.current, s.freezes_used) == (3, 1)


def test_freezes_are_not_spent_before_the_first_active_day() -> None:
    s = compute_streak(_days(0), TODAY, freezes=3)
    assert (s.current, s.freezes_used) == (1, 0)


def test_future_days_are_ignored_and_empty_history_is_zero() -> None:
    assert compute_streak([], TODAY).current == 0
    assert compute_streak([TODAY + timedelta(days=1)], TODAY).current == 0


def test_weekly_mode_counts_iso_weeks() -> None:
    # 2026-10-13 is a Tuesday: one day in each of the last three weeks.
    s = compute_streak(_days(0, 7, 14), TODAY, mode=StreakMode.WEEKLY)
    assert s.current == 3
    assert compute_streak(_days(0, 14), TODAY, mode=StreakMode.WEEKLY).current == 1


@given(st.sets(st.integers(min_value=0, max_value=60)), st.integers(min_value=0, max_value=3))
def test_current_never_exceeds_active_days_plus_freezes(offsets: set[int], freezes: int) -> None:
    s = compute_streak(_days(*offsets), TODAY, freezes=freezes)
    assert s.current <= len(offsets)
    assert s.freezes_used <= freezes
    assert s.longest >= s.current


def test_consecutive_dailies_differ() -> None:
    import itertools
    import uuid
    from datetime import UTC, datetime, timedelta

    from devgrill.domain.enums import ChallengeKind
    from devgrill.infra.repositories.challenges import pick_for, window

    day = datetime(2026, 10, 1, 12, tzinfo=UTC)
    for size in (2, 3, 7):
        pool = [uuid.uuid4() for _ in range(size)]
        picks = [
            pick_for(ChallengeKind.DAILY, window(ChallengeKind.DAILY, day + timedelta(i)), pool)
            for i in range(200)
        ]
        assert all(a != b for a, b in itertools.pairwise(picks))
        assert set(picks) == set(pool)  # the whole rotation gets played


def test_calibration_starts_from_experience_and_moves_one_step() -> None:
    from devgrill.domain import calibration
    from devgrill.domain.enums import ExperienceLevel

    out = calibration.starting_ratings(
        ExperienceLevel.Y2_5, ["caching", "queues", "memory"], {"caching": True, "queues": False}
    )
    base = calibration.BASE[ExperienceLevel.Y2_5]
    assert out["caching"].rating == base + calibration.STEP
    assert out["queues"].rating == base - calibration.STEP
    assert out["memory"].rating == base
    # Loosely held: answered tracks a little surer than experience alone, both unsure.
    assert out["caching"].rd == calibration.RD_ANSWERED < out["memory"].rd < 350
    assert calibration.starting_ratings(None, ["x"], {})["x"].rating == 1500.0
