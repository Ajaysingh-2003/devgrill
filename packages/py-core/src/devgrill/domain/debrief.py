"""The debrief's reading of an attempt (ADR 015): the investigation replay and the approach.

Both are rules authored with the scenario until phase 6 adds the AI:
  - replay markers come from `ScenarioSpec.replay` (a trigger plus an optional pattern),
    and every hint taken is marked;
  - the player's approach is the first `approaches/` entry whose `match` holds.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal

from devgrill.domain.events import event_text, event_triggers
from devgrill.domain.spec import ApproachMatch, ReplayRule

Mark = Literal["clue", "lost", "hint"]

#: Event types the replay reads (others are bookkeeping or teammates' lines).
REPLAY_TYPES: Final = (
    "alert",
    "action",
    "deploy",
    "rollback",
    "trail",
    "hint",
    "message",
    "mitigation",
    "state",
    "verify",
)


@dataclass(frozen=True, slots=True)
class TrailEvent:
    ts: datetime
    type: str
    payload: dict[str, Any]
    #: The attempt_events row (coach notes cite it).
    id: int | None = None


@dataclass(frozen=True, slots=True)
class ReplayEntry:
    #: Seconds since the page (negative before it).
    at_s: float
    text: str
    mark: Mark | None = None
    note: str | None = None
    event_id: int | None = None


def replay(
    events: Iterable[TrailEvent], paged_at: datetime | None, rules: Sequence[ReplayRule]
) -> list[ReplayEntry]:
    """The player's incident in order, with the scenario's markers on the moments that matter."""
    entries: list[ReplayEntry] = []
    start = paged_at
    for event in sorted(events, key=lambda e: e.ts):
        text = event_text(event.type, event.payload)
        if text is None:
            continue
        if start is None:
            start = event.ts
        mark: Mark | None = None
        note: str | None = None
        triggers = event_triggers(event.type, event.payload)
        for rule in rules:
            if rule.when in triggers and (rule.match is None or re.search(rule.match, text, re.I)):
                mark, note = rule.mark, rule.note
                break
        if mark is None and event.type == "hint":
            mark, note = "hint", "Hints lower the score a little; they still beat guessing."
        at_s = round((event.ts - start).total_seconds(), 1)
        entries.append(ReplayEntry(at_s, text, mark, note, event.id))
    return entries


def match_approach(
    approaches: Sequence[tuple[str, ApproachMatch | None]],
    *,
    rolled_back: bool,
    diffs: Sequence[str],
) -> str | None:
    """The key of the first approach whose rule holds for this attempt, if any."""
    deployed = "\n".join(diffs)
    for key, rule in approaches:
        if rule is None:
            continue
        if rule.rollback is not None and rule.rollback != rolled_back:
            continue
        if rule.diff is not None and not re.search(rule.diff, deployed, re.M):
            continue
        return key
    return None
