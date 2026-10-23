"""Who may start a live sandbox, for how long, and when not (ADR 013).

Pure policy: callers gather usage from the database and fleet state, `decide` answers. Four
independent caps, checked in order, each with its own refusal:

1. access     the scenario is in the plan (guests: tutorial only)  -> 403
2. per user   one live sandbox; starts and minutes per day/week     -> 409 / 429
3. fleet      sandboxes alive across everyone                        -> 503 capacity
4. money      free + guest minutes per IST day, and a kill switch   -> 503 budget_paused

Days and weeks roll over at 00:00 Asia/Kolkata (weeks start on Monday), like streaks. A
granted session never outlives the user's remaining minutes: its TTL is capped by them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any, Final, Literal
from zoneinfo import ZoneInfo

from devgrill.domain.enums import Access

IST: Final = ZoneInfo("Asia/Kolkata")

Tier = Literal["guest", "free", "pro", "team"]
Period = Literal["day", "week", "ever"]
Refusal = Literal[
    "sign_up_required",
    "upgrade_required",
    "active_attempt_exists",
    "quota_exceeded",
    "capacity",
    "budget_paused",
]

#: A session shorter than this isn't worth booting; refuse instead of granting a stub.
MIN_SESSION_MINUTES: Final = 5


@dataclass(frozen=True, slots=True)
class PlanLimits:
    #: "free" plays `access: free` scenarios (plus the Daily); "all" plays everything.
    live_access: Literal["tutorial", "free", "all"]
    concurrent_sandboxes: int
    live_starts: int
    live_starts_period: Period
    sandbox_minutes: int
    sandbox_minutes_period: Period
    ttl_minutes: int
    idle_minutes: int
    extend_minutes: int
    max_extends: int
    ai_messages_per_day: int
    postmortem_reviews: int
    postmortem_reviews_period: Period
    #: Counts towards the global free budget (layer 4).
    budgeted: bool

    def with_overrides(self, overrides: dict[str, Any] | None) -> PlanLimits:
        """Apply `entitlements.limits` (a JSON object of field overrides; unknown keys ignored)."""
        if not overrides:
            return self
        known = {k: v for k, v in overrides.items() if k in self.__dataclass_fields__}
        return replace(self, **known)


DEFAULT_LIMITS: Final[dict[Tier, PlanLimits]] = {
    "guest": PlanLimits(
        live_access="tutorial",
        concurrent_sandboxes=1,
        live_starts=1,
        live_starts_period="ever",
        sandbox_minutes=20,
        sandbox_minutes_period="ever",
        ttl_minutes=20,
        idle_minutes=5,
        extend_minutes=0,
        max_extends=0,
        ai_messages_per_day=10,
        postmortem_reviews=0,
        postmortem_reviews_period="week",
        budgeted=True,
    ),
    "free": PlanLimits(
        live_access="free",
        concurrent_sandboxes=1,
        live_starts=3,
        live_starts_period="week",
        sandbox_minutes=120,
        sandbox_minutes_period="week",
        ttl_minutes=30,
        idle_minutes=8,
        extend_minutes=0,
        max_extends=0,
        ai_messages_per_day=20,
        postmortem_reviews=2,
        postmortem_reviews_period="week",
        budgeted=True,
    ),
    "pro": PlanLimits(
        live_access="all",
        concurrent_sandboxes=1,
        live_starts=10,
        live_starts_period="day",
        sandbox_minutes=240,
        sandbox_minutes_period="day",
        ttl_minutes=60,
        idle_minutes=10,
        extend_minutes=15,
        max_extends=2,
        ai_messages_per_day=200,
        postmortem_reviews=20,
        postmortem_reviews_period="day",
        budgeted=False,
    ),
    "team": PlanLimits(
        live_access="all",
        concurrent_sandboxes=1,
        live_starts=10,
        live_starts_period="day",
        sandbox_minutes=240,
        sandbox_minutes_period="day",
        ttl_minutes=60,
        idle_minutes=10,
        extend_minutes=15,
        max_extends=2,
        ai_messages_per_day=200,
        postmortem_reviews=20,
        postmortem_reviews_period="day",
        budgeted=False,
    ),
}


def limits_for(tier: Tier, overrides: dict[str, Any] | None = None) -> PlanLimits:
    return DEFAULT_LIMITS[tier].with_overrides(overrides)


# ---------------------------------------------------------------------------- periods


def period_start(now: datetime, period: Period) -> datetime | None:
    """Start of the current IST day or week (Monday), as an aware datetime; None for "ever"."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if period == "ever":
        return None
    local = now.astimezone(IST)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        start -= timedelta(days=start.weekday())
    return start


def next_rollover(now: datetime, period: Period) -> datetime | None:
    start = period_start(now, period)
    if start is None:
        return None
    return start + timedelta(days=7 if period == "week" else 1)  # IST has no DST


def seconds_until(now: datetime, when: datetime | None) -> int | None:
    if when is None:
        return None
    return max(1, math.ceil((when - now).total_seconds()))


# ---------------------------------------------------------------------------- decision


@dataclass(frozen=True, slots=True)
class Usage:
    """What this user (or guest token) already used, counted by the caller per the periods."""

    live_now: int
    starts_in_period: int
    minutes_in_period: float


@dataclass(frozen=True, slots=True)
class Fleet:
    live_total: int
    max_live: int
    #: Minutes used today (IST) by budgeted tiers, across everyone.
    budgeted_minutes_today: float
    daily_budget_minutes: int
    free_starts_enabled: bool


@dataclass(frozen=True, slots=True)
class StartRequest:
    tier: Tier
    limits: PlanLimits
    scenario_access: Access
    #: Today's Daily Incident is open to every signed-in plan (it still counts as usage).
    is_daily: bool
    #: The scenario is on the guest tutorial list.
    is_tutorial: bool
    #: The scenario's own TTL, if it sets one.
    scenario_ttl_minutes: int | None
    usage: Usage
    fleet: Fleet
    now: datetime


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    refusal: Refusal | None = None
    detail: str = ""
    retry_after_s: int | None = None
    ttl_minutes: int = 0
    idle_minutes: int = 0
    #: When a refusal lifts on its own (a plan period or the free daily budget resets).
    resets_at: datetime | None = None

    @property
    def status(self) -> int:
        return {
            None: 202,
            "sign_up_required": 403,
            "upgrade_required": 403,
            "active_attempt_exists": 409,
            "quota_exceeded": 429,
            "capacity": 503,
            "budget_paused": 503,
        }[self.refusal]


def _deny(
    refusal: Refusal,
    detail: str,
    retry_after_s: int | None = None,
    resets_at: datetime | None = None,
) -> Decision:
    return Decision(False, refusal, detail, retry_after_s, resets_at=resets_at)


def _in_plan(req: StartRequest) -> bool:
    access = req.limits.live_access
    if access == "all":
        return True
    if access == "tutorial":
        return req.is_tutorial
    return req.scenario_access is Access.FREE or req.is_daily or req.is_tutorial


def decide(req: StartRequest) -> Decision:
    limits, usage, fleet, now = req.limits, req.usage, req.fleet, req.now

    # 1. access
    if not _in_plan(req):
        if req.tier == "guest":
            return _deny("sign_up_required", "Sign in to play this one. It's free.")
        return _deny(
            "upgrade_required",
            "This one is part of Pro. On the free plan you can play the free drills and the Daily.",
        )

    # 2. per user
    if usage.live_now >= limits.concurrent_sandboxes:
        return _deny(
            "active_attempt_exists",
            "You're already in the middle of one. Finish it or leave it first.",
        )
    if usage.starts_in_period >= limits.live_starts:
        reset = next_rollover(now, limits.live_starts_period)
        return _deny(
            "quota_exceeded",
            _plays_text(req.tier, limits.live_starts, limits.live_starts_period),
            seconds_until(now, reset),
            reset,
        )
    remaining = limits.sandbox_minutes - usage.minutes_in_period
    if remaining < MIN_SESSION_MINUTES:
        reset = next_rollover(now, limits.sandbox_minutes_period)
        return _deny(
            "quota_exceeded",
            _time_text(limits.sandbox_minutes, limits.sandbox_minutes_period),
            seconds_until(now, reset),
            reset,
        )

    # 3. fleet
    if fleet.live_total >= fleet.max_live:
        return _deny("capacity", "Everyone's practising right now. Try again in a minute.", 60)

    # 4. money (budgeted tiers only)
    if limits.budgeted:
        tomorrow = next_rollover(now, "day")
        if not fleet.free_starts_enabled:
            return _deny(
                "budget_paused",
                "Free play is paused for a while. Quick Fire is still open.",
                3600,
            )
        if fleet.budgeted_minutes_today >= fleet.daily_budget_minutes:
            return _deny(
                "budget_paused",
                "Free play is full for today. Quick Fire is still open.",
                seconds_until(now, tomorrow),
                tomorrow,
            )

    ttl = min(
        limits.ttl_minutes, req.scenario_ttl_minutes or limits.ttl_minutes, math.floor(remaining)
    )
    return Decision(True, ttl_minutes=ttl, idle_minutes=min(limits.idle_minutes, ttl))


_PER = {"day": "today", "week": "this week", "ever": "on your plan"}


def _plays_text(tier: Tier, amount: int, period: Period) -> str:
    kind = "free " if tier in ("guest", "free") else ""
    plays = "play" if amount == 1 else "plays"
    return f"You've used your {amount} {kind}{plays} {_PER[period]}."


def _time_text(minutes: int, period: Period) -> str:
    hours = minutes / 60
    amount = f"{hours:g} hours" if hours >= 2 else f"{minutes} minutes"
    return f"You've used your {amount} of practice time {_PER[period]}."
