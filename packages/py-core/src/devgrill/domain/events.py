"""What happens during an attempt: event types, who may see them, and which beats they fire.

Every in-world thing (a page, a teammate's message, a deploy, a hint) is an `attempt_events`
row. The workspace streams them (SSE) to build the war room, the timeline and the boot
sequence. A few types are for the platform only and never reach the player.

Triggers name what just happened, for beats with `when:` (scenario spec v1):
  state:<state>          the attempt moved (state:active, state:mitigated...)
  <service>.restarted    a service was restarted (CLI or UI)
  <service>.deployed     a deploy went live
  <service>.rolledback   a rollback went live
  hint:<tier>            the player took a hint
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from devgrill.domain.spec import Beat

#: Never streamed to the player: they would spoil the incident or are internal bookkeeping.
#: "trail" is the investigation trail (console queries...): kept for scoring and the AI.
HIDDEN_TYPES: Final = frozenset({"fault", "health", "trail"})

#: Shown in the incident timeline (the rest drive state, the boot sequence or the war room).
TIMELINE_TYPES: Final = frozenset(
    {"alert", "beat", "message", "action", "deploy", "rollback", "hint", "mitigation", "state"}
)


def visible(event_type: str) -> bool:
    return event_type not in HIDDEN_TYPES


def state_trigger(state: str) -> str:
    return f"state:{state}"


def beats_for_trigger(
    beats: Sequence[Beat], trigger: str, already_fired: Iterable[int]
) -> list[tuple[int, Beat]]:
    """Beats (with their index in the spec) that `trigger` fires and that haven't fired yet."""
    fired = set(already_fired)
    return [(i, b) for i, b in enumerate(beats) if b.when == trigger and i not in fired]


def timed_beats(beats: Sequence[Beat]) -> list[tuple[int, int, Beat]]:
    """(seconds after T, index, beat) for beats with `at:`, in firing order."""
    out = [(b.at_seconds, i, b) for i, b in enumerate(beats) if b.at is not None]
    return sorted(out, key=lambda item: (item[0], item[1]))
