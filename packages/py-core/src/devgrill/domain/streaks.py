"""Streaks, derived from the days a user was active (PLAN §8.5: never sold, no guilt).

`activity_days` is the source of truth; streaks are recomputed from it, never incremented.
A day is the user's local calendar day (India-first: Asia/Kolkata unless the user set a
timezone). The current day or week never breaks a streak while it is still in progress.

The history is replayed oldest first:
  - an active day (or week) extends the run, and every `EARN_EVERY` of them in a row earns a
    freeze, up to `MAX_FREEZES` held;
  - a missed one spends a freeze if one is held (the run survives, without growing), else
    the run starts over;
  - an on-call leave day is neutral: it neither extends nor breaks the run. In weekly mode a
    week counts as leave only when every day of it is.
Freezes are only ever earned by playing, and spend themselves.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from devgrill.domain.enums import StreakMode

DEFAULT_TIMEZONE: Final = "Asia/Kolkata"


#: Active periods in a row that earn one freeze (days, or weeks in weekly mode).
EARN_EVERY: Final[dict[StreakMode, int]] = {StreakMode.DAILY: 7, StreakMode.WEEKLY: 4}
#: Freezes held at most (PLAN §8.5: "2 earnable freezes").
MAX_FREEZES: Final = 2


@dataclass(frozen=True, slots=True)
class StreakSummary:
    current: int
    longest: int
    last_day: date | None
    #: Spent bridging misses in the current run.
    freezes_used: int
    #: Held now, ready for the next miss.
    freezes: int = 0


def activity_day(at: datetime, timezone: str = DEFAULT_TIMEZONE) -> date:
    """The local calendar day of an aware timestamp."""
    if at.tzinfo is None:
        raise ValueError("activity timestamps must be timezone-aware")
    return at.astimezone(ZoneInfo(timezone)).date()


def _period(day: date, mode: StreakMode) -> int:
    """A sortable index: one per day, or one per ISO week (weeks start on Monday)."""
    if mode is StreakMode.DAILY:
        return day.toordinal()
    monday = day - timedelta(days=day.weekday())
    return monday.toordinal() // 7


def _leave_periods(leave: Iterable[date], mode: StreakMode) -> set[int]:
    days = set(leave)
    if mode is StreakMode.DAILY:
        return {d.toordinal() for d in days}
    weeks: dict[int, int] = {}
    for d in days:
        weeks[_period(d, mode)] = weeks.get(_period(d, mode), 0) + 1
    return {w for w, n in weeks.items() if n == 7}


def compute_streak(
    days: Iterable[date],
    today: date,
    *,
    mode: StreakMode = StreakMode.DAILY,
    freezes: int = 0,
    leave: Iterable[date] = (),
) -> StreakSummary:
    """Current and longest streak as of `today` (the user's local date).

    `freezes` are held before the first active day (kept for grants; play earns the rest).
    """
    active_days = sorted({d for d in days if d <= today})
    if not active_days:
        return StreakSummary(current=0, longest=0, last_day=None, freezes_used=0, freezes=0)

    active = {_period(d, mode) for d in active_days}
    on_leave = _leave_periods(leave, mode) - active
    now = _period(today, mode)
    earn_every = EARN_EVERY[mode]

    run = longest = used = 0
    held = freezes
    for p in range(min(active), now + 1):
        if p in active:
            run += 1
            if run % earn_every == 0 and held < MAX_FREEZES:
                held += 1
        elif p == now or p in on_leave:
            continue  # still in progress, or on leave: neutral
        elif held > 0:
            held -= 1
            used += 1
        else:
            run = used = 0
        longest = max(longest, run)

    return StreakSummary(
        current=run, longest=longest, last_day=active_days[-1], freezes_used=used, freezes=held
    )
