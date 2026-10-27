"""When the daily email may go out (PLAN §8.5: at most one a day, quiet hours, one-tap pause).

Pure rules; the worker's hourly sweep asks `due()` per player and the database caps each kind
at one row per local day (notifications_sent), so a retried sweep can't send twice.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Final
from zoneinfo import ZoneInfo

#: Never send between these local hours (22:00 to 08:00).
QUIET_START: Final = 22
QUIET_END: Final = 8
#: Send hours a player can pick (local time); all outside quiet hours.
SEND_HOURS: Final = (8, 9, 13, 18, 21)
DEFAULT_SEND_HOUR: Final = 9


def in_quiet_hours(hour: int) -> bool:
    return hour >= QUIET_START or hour < QUIET_END


def local_day(now: datetime, timezone: str) -> date:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(ZoneInfo(timezone)).date()


def due(now: datetime, *, enabled: bool, timezone: str, send_hour: int, sent_today: bool) -> bool:
    """Whether a player's digest should go out in the sweep running at `now`.

    From their send hour onwards (a late sweep still sends that day), never in quiet hours,
    never twice in a local day, never when they turned it off.
    """
    if not enabled or sent_today:
        return False
    hour = now.astimezone(ZoneInfo(timezone)).hour
    return not in_quiet_hours(hour) and hour >= send_hour
