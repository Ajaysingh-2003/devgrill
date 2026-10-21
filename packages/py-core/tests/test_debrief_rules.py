"""The debrief's rules (ADR 015): replay markers, approach recognition, the postmortem format."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from devgrill.domain import postmortem as pm
from devgrill.domain.debrief import TrailEvent, match_approach, replay
from devgrill.domain.spec import ApproachMatch, ReplayRule

PAGED = datetime(2026, 10, 21, 20, 0, tzinfo=UTC)


def at(seconds: int) -> datetime:
    return PAGED + timedelta(seconds=seconds)


def test_replay_marks_what_the_scenario_cares_about() -> None:
    rules = [
        ReplayRule(when="postgres-db.restarted", mark="lost", note="The victim, not the cause."),
        ReplayRule(when="db.query", match="pg_stat_statements", mark="clue", note="Who reads?"),
    ]
    events = [
        TrailEvent(at(0), "alert", {"title": "p99 > 1.5s"}),
        TrailEvent(at(60), "action", {"verb": "restart", "service": "postgres-db"}),
        TrailEvent(at(90), "trail", {"verb": "sql", "query": "select 1"}),
        TrailEvent(at(120), "trail", {"verb": "sql", "query": "select * from pg_stat_statements"}),
        TrailEvent(at(150), "hint", {"tier": 1}),
        TrailEvent(at(170), "beat", {"say": "teammates are not the player's trail"}),
        TrailEvent(at(200), "rollback", {"service": "api", "ref": "abc", "ok": True}),
    ]
    out = replay(events, PAGED, rules)
    assert [(e.at_s, e.mark) for e in out] == [
        (0.0, None),
        (60.0, "lost"),
        (90.0, None),
        (120.0, "clue"),
        (150.0, "hint"),
        (200.0, None),
    ]
    assert out[1].text == "Restarted postgres-db"
    assert out[1].note == "The victim, not the cause."


def test_the_first_matching_approach_wins() -> None:
    rules = [
        ("restore-ttl", ApproachMatch(diff=r"^\+CACHE_TTL_SECONDS=[1-9]")),
        ("rollback", ApproachMatch(rollback=True)),
        ("unmatched", None),
    ]
    fix = "--- config/app.env\n+++ config/app.env\n-CACHE_TTL_SECONDS=0\n+CACHE_TTL_SECONDS=300\n"
    assert match_approach(rules, rolled_back=True, diffs=[fix]) == "restore-ttl"
    assert match_approach(rules, rolled_back=True, diffs=[]) == "rollback"
    assert match_approach(rules, rolled_back=False, diffs=["+# a comment\n"]) is None


def test_postmortem_sections_round_trip_with_the_timeline() -> None:
    sections = {"summary": "Reads hit Postgres.", "cause": "TTL 0.\n\nSince the ops deploy."}
    body = pm.to_markdown(sections, ["00:00 Paged", "04:10 Rolled api back"])
    assert body.startswith("## Summary\n\nReads hit Postgres.")
    assert "## Timeline\n\n- 00:00 Paged\n- 04:10 Rolled api back" in body
    assert pm.from_markdown(body) == {
        "summary": "Reads hit Postgres.",
        "impact": "",
        "cause": "TTL 0.\n\nSince the ops deploy.",
        "actions": "",
    }
    assert pm.clock(-30) == "-00:30" and pm.clock(754) == "12:34"
