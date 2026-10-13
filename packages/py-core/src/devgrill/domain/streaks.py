"""Streaks, derived from the days a user was active.

`activity_days` is the source of truth; streaks are recomputed from it, never incremented.
A day is the user's local calendar day (India-first: Asia/Kolkata unless the user set a
timezone). The current day or week never breaks a streak while it is still in progress.
Freezes bridge missed periods: each one covers a single missed day (or week) between two
active ones.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from devgrill.domain.enums import StreakMode

DEFAULT_TIMEZONE: Final = "Asia/Kolkata"


@dataclass(frozen=True, slots=True)
class StreakSummary:
    current: int
    longest: int
    last_day: date | None
    freezes_used: int


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


def _longest_run(periods: list[int]) -> int:
    best = run = 0
    previous: int | None = None
    for p in periods:
        run = run + 1 if previous is not None and p == previous + 1 else 1
        best = max(best, run)
        previous = p
    return best


def compute_streak(
    days: Iterable[date],
    today: date,
    *,
    mode: StreakMode = StreakMode.DAILY,
    freezes: int = 0,
) -> StreakSummary:
    """Current and longest streak as of `today` (the user's local date)."""
    active_days = sorted({d for d in days if d <= today})
    if not active_days:
        return StreakSummary(current=0, longest=0, last_day=None, freezes_used=0)

    periods = sorted({_period(d, mode) for d in active_days})
    active = set(periods)
    earliest = periods[0]
    now = _period(today, mode)

    current = 0
    freezes_left = freezes
    used = 0
    p = now
    while p >= earliest:
        if p in active:
            current += 1
        elif p == now:
            pass  # today (or this week) isn't over yet: not a miss
        elif freezes_left > 0 and any(q < p for q in active):
            freezes_left -= 1
            used += 1
        else:
            break
        p -= 1

    longest = max(_longest_run(periods), current)
    return StreakSummary(
        current=current, longest=longest, last_day=active_days[-1], freezes_used=used
    )
