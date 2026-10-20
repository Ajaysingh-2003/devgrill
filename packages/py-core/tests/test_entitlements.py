"""The sandbox entitlement policy (ADR 013): every refusal, the IST rollover, TTL capping."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from devgrill.domain.entitlements import (
    IST,
    Fleet,
    StartRequest,
    Tier,
    Usage,
    decide,
    limits_for,
    next_rollover,
    period_start,
)
from devgrill.domain.enums import Access

# Wednesday 2026-10-21 10:00 IST
NOW = datetime(2026, 10, 21, 4, 30, tzinfo=UTC)
ROOMY = Fleet(
    live_total=0,
    max_live=4,
    budgeted_minutes_today=0,
    daily_budget_minutes=600,
    free_starts_enabled=True,
)


def request(tier: Tier = "free", access: Access = Access.FREE, **kw: Any) -> StartRequest:
    base = StartRequest(
        tier=tier,
        limits=limits_for(tier),
        scenario_access=access,
        is_daily=False,
        is_tutorial=False,
        scenario_ttl_minutes=None,
        usage=Usage(live_now=0, starts_in_period=0, minutes_in_period=0),
        fleet=ROOMY,
        now=NOW,
    )
    return replace(base, **kw)


def test_free_plays_free_scenarios_with_plan_ttl():
    decision = decide(request())
    assert decision.allowed and decision.status == 202
    assert (decision.ttl_minutes, decision.idle_minutes) == (30, 8)


def test_free_cannot_play_pro_but_can_play_the_daily():
    denied = decide(request(access=Access.PRO))
    assert (denied.refusal, denied.status) == ("upgrade_required", 403)
    assert decide(request(access=Access.PRO, is_daily=True)).allowed


def test_pro_plays_everything():
    assert decide(request(tier="pro", access=Access.PRO)).allowed


def test_guests_only_play_the_tutorial():
    assert decide(request(tier="guest", access=Access.FREE)).refusal == "sign_up_required"
    granted = decide(request(tier="guest", access=Access.FREE, is_tutorial=True))
    assert granted.allowed and granted.ttl_minutes == 20


def test_one_live_sandbox():
    decision = decide(request(usage=Usage(live_now=1, starts_in_period=0, minutes_in_period=0)))
    assert (decision.refusal, decision.status) == ("active_attempt_exists", 409)


def test_weekly_starts_quota_retries_at_monday_midnight_ist():
    decision = decide(request(usage=Usage(live_now=0, starts_in_period=3, minutes_in_period=10)))
    assert (decision.refusal, decision.status) == ("quota_exceeded", 429)
    monday = datetime(2026, 10, 26, 0, 0, tzinfo=IST)
    assert decision.retry_after_s == int((monday - NOW).total_seconds())


def test_minutes_quota_and_ttl_capped_by_what_is_left():
    capped = decide(request(usage=Usage(live_now=0, starts_in_period=1, minutes_in_period=108)))
    assert capped.allowed and capped.ttl_minutes == 12
    spent = decide(request(usage=Usage(live_now=0, starts_in_period=1, minutes_in_period=117)))
    assert spent.refusal == "quota_exceeded"


def test_scenario_ttl_shortens_the_session():
    assert decide(request(scenario_ttl_minutes=20)).ttl_minutes == 20
    assert decide(request(scenario_ttl_minutes=120)).ttl_minutes == 30


def test_fleet_capacity_applies_to_everyone():
    full = replace(ROOMY, live_total=4)
    cases: tuple[tuple[Tier, Access], ...] = (("free", Access.FREE), ("pro", Access.PRO))
    for tier, access in cases:
        decision = decide(request(tier=tier, access=access, fleet=full))
        assert (decision.refusal, decision.status, decision.retry_after_s) == ("capacity", 503, 60)


def test_budget_pauses_free_but_not_pro():
    spent = replace(ROOMY, budgeted_minutes_today=600)
    free = decide(request(fleet=spent))
    assert (free.refusal, free.status) == ("budget_paused", 503)
    tomorrow = datetime(2026, 10, 22, 0, 0, tzinfo=IST)
    assert free.retry_after_s == int((tomorrow - NOW).total_seconds())
    assert decide(request(tier="pro", access=Access.PRO, fleet=spent)).allowed


def test_kill_switch_stops_free_and_guest_starts():
    off = replace(ROOMY, free_starts_enabled=False)
    assert decide(request(fleet=off)).refusal == "budget_paused"
    assert decide(request(tier="guest", is_tutorial=True, fleet=off)).refusal == "budget_paused"
    assert decide(request(tier="pro", fleet=off)).allowed


def test_refusals_are_checked_in_order():
    # Not in the plan wins over everything else.
    everything_wrong = request(
        access=Access.PRO,
        usage=Usage(live_now=1, starts_in_period=9, minutes_in_period=999),
        fleet=replace(ROOMY, live_total=99, free_starts_enabled=False),
    )
    assert decide(everything_wrong).refusal == "upgrade_required"


def test_overrides_from_the_entitlements_row():
    limits = limits_for("free", {"live_starts": 10, "unknown_key": 1})
    assert limits.live_starts == 10 and limits.sandbox_minutes == 120


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("day", datetime(2026, 10, 21, 0, 0, tzinfo=IST)),
        ("week", datetime(2026, 10, 19, 0, 0, tzinfo=IST)),
    ],
)
def test_periods_start_at_ist_midnight(period, expected):
    assert period_start(NOW, period) == expected


def test_ist_day_differs_from_utc_day():
    # 2026-10-21 20:00 UTC is already the 22nd in India.
    late = datetime(2026, 10, 21, 20, 0, tzinfo=UTC)
    assert period_start(late, "day") == datetime(2026, 10, 22, 0, 0, tzinfo=IST)
    assert next_rollover(late, "day") == datetime(2026, 10, 23, 0, 0, tzinfo=IST)
    assert period_start(late, "ever") is None and next_rollover(late, "ever") is None


def test_naive_now_is_rejected():
    with pytest.raises(ValueError):
        period_start(datetime(2026, 10, 21), "day")
