"""Streak and digest rules, property-tested (phase 7 gate: time zones, DST, freezes, leave days,
notification caps)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from hypothesis import given, settings
from hypothesis import strategies as st

from devgrill.domain import digest
from devgrill.domain.enums import StreakMode
from devgrill.domain.streaks import EARN_EVERY, MAX_FREEZES, activity_day, compute_streak

TODAY = date(2026, 10, 27)
offsets = st.sets(st.integers(min_value=0, max_value=90), max_size=60)
modes = st.sampled_from([StreakMode.DAILY, StreakMode.WEEKLY])


def _days(offs: set[int]) -> list[date]:
    return [TODAY - timedelta(days=o) for o in offs]


def _trailing_run(offs: set[int]) -> int:
    """The plain definition: consecutive active days ending today or yesterday."""
    start = 0 if 0 in offs else 1
    n = 0
    while start + n in offs:
        n += 1
    return n


# ------------------------------------------------------------------------- examples


def test_seven_days_earn_a_freeze_that_bridges_a_miss() -> None:
    # Active 10..4 days ago (7 in a row), missed 3 days ago, active 2..0.
    s = compute_streak(_days({10, 9, 8, 7, 6, 5, 4, 2, 1, 0}), TODAY)
    assert (s.current, s.freezes_used, s.freezes) == (10, 1, 0)


def test_six_days_earn_nothing() -> None:
    s = compute_streak(_days({9, 8, 7, 6, 5, 4, 2, 1, 0}), TODAY)
    assert s.current == 3


def test_freezes_are_capped() -> None:
    s = compute_streak(_days(set(range(40))), TODAY)
    assert s.freezes == MAX_FREEZES


def test_leave_is_neutral() -> None:
    days = _days({5, 4, 1, 0})
    leave = _days({3, 2})
    s = compute_streak(days, TODAY, leave=leave)
    assert (s.current, s.freezes_used) == (4, 0)
    assert compute_streak(days, TODAY).current == 2


def test_weekly_leave_needs_the_whole_week() -> None:
    # TODAY is Tuesday 27 Oct. Active this week and in the week of 5 Oct (6 Oct, 21 days ago);
    # the weeks of 12 Oct (offsets 9..15) and 19 Oct (offsets 2..8) were missed.
    days = _days({0, 21})
    weekly = StreakMode.WEEKLY
    whole = _days(set(range(2, 16)))
    assert compute_streak(days, TODAY, mode=weekly, leave=whole).current == 2
    # One day short of the second whole week: that week is a miss, and the run starts over.
    assert compute_streak(days, TODAY, mode=weekly, leave=_days(set(range(2, 15)))).current == 1


# ------------------------------------------------------------------------- properties


@given(offsets, modes)
def test_basic_invariants(offs: set[int], mode: StreakMode) -> None:
    s = compute_streak(_days(offs), TODAY, mode=mode)
    assert 0 <= s.current <= s.longest
    assert 0 <= s.freezes <= MAX_FREEZES
    # A freeze is earned per EARN_EVERY active periods, so spending can't outrun earning.
    assert s.freezes_used <= max(0, s.current // EARN_EVERY[mode]) + MAX_FREEZES
    assert s.current <= len({_period_of(d, mode) for d in _days(offs)})


def _period_of(d: date, mode: StreakMode) -> int:
    return (
        d.toordinal() if mode is StreakMode.DAILY else (d - timedelta(days=d.weekday())).toordinal()
    )


@given(offsets)
def test_freezes_only_ever_help(offs: set[int]) -> None:
    s = compute_streak(_days(offs), TODAY)
    assert s.current >= _trailing_run(offs)
    if s.freezes_used == 0:
        assert s.current == _trailing_run(offs)


@given(offsets, st.integers(min_value=1, max_value=90))
def test_more_activity_never_shortens_the_streak(offs: set[int], extra: int) -> None:
    before = compute_streak(_days(offs), TODAY).current
    after = compute_streak(_days(offs | {extra}), TODAY).current
    assert after >= before


@given(offsets, st.sets(st.integers(min_value=1, max_value=90), max_size=20))
def test_leave_never_shortens_the_streak(offs: set[int], leave: set[int]) -> None:
    without = compute_streak(_days(offs), TODAY).current
    with_leave = compute_streak(_days(offs), TODAY, leave=_days(leave)).current
    assert with_leave >= without


@given(offsets)
def test_today_unplayed_never_breaks_the_streak(offs: set[int]) -> None:
    # Played yesterday, not yet today: the streak stands as it was at the end of yesterday.
    days = _days({o for o in offs if o >= 1} | {1})
    assert compute_streak(days, TODAY) == compute_streak(days, TODAY - timedelta(days=1))


@settings(max_examples=60)
@given(
    st.sampled_from(["Asia/Kolkata", "America/New_York", "Europe/London", "Australia/Sydney"]),
    st.lists(st.integers(min_value=0, max_value=23 * 60 + 59), min_size=30, max_size=30),
)
def test_one_play_per_local_day_is_unbroken_across_dst(zone: str, minutes: list[int]) -> None:
    """Thirty local days spanning a DST change, one play a day at any local time: 30 in a row."""
    tz = ZoneInfo(zone)
    first = date(2026, 10, 15)  # US/EU clocks change in late October / early November
    plays = []
    for i, m in enumerate(minutes):
        local = datetime.combine(first + timedelta(days=i), time(m // 60, m % 60), tzinfo=tz)
        plays.append(local.astimezone(UTC))  # stored as UTC, as the API does
    days = [activity_day(at, zone) for at in plays]
    assert len(set(days)) == 30
    assert compute_streak(days, first + timedelta(days=29)).current == 30


# ------------------------------------------------------------------------- digest caps


@given(
    st.datetimes(
        min_value=datetime(2026, 1, 1), max_value=datetime(2026, 12, 31), timezones=st.just(UTC)
    ),
    st.sampled_from(["Asia/Kolkata", "America/New_York", "UTC", "Pacific/Auckland"]),
    st.sampled_from(digest.SEND_HOURS),
)
def test_digest_never_in_quiet_hours_or_twice(now: datetime, zone: str, hour: int) -> None:
    local_hour = now.astimezone(ZoneInfo(zone)).hour
    sent = digest.due(now, enabled=True, timezone=zone, send_hour=hour, sent_today=False)
    if sent:
        assert not digest.in_quiet_hours(local_hour)
        assert local_hour >= hour
    assert not digest.due(now, enabled=True, timezone=zone, send_hour=hour, sent_today=True)
    assert not digest.due(now, enabled=False, timezone=zone, send_hour=hour, sent_today=False)


def test_an_hourly_sweep_sends_at_most_once_per_local_day() -> None:
    zone = "Asia/Kolkata"
    sent_days: list[date] = []
    at = datetime(2026, 10, 1, tzinfo=UTC)
    for _ in range(24 * 14):
        day = digest.local_day(at, zone)
        if digest.due(at, enabled=True, timezone=zone, send_hour=9, sent_today=day in sent_days):
            sent_days.append(day)
        at += timedelta(hours=1)
    assert len(sent_days) == len(set(sent_days)) == 14
