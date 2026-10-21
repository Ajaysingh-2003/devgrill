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
Plus, for the debrief's replay rules (ScenarioSpec.replay), which beats don't use:
  db.query               a query in the Database console
  message                a status update in the war room
  mitigation.declared    the player declared the incident mitigated
  verify.passed / verify.failed
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Final

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


def event_triggers(event_type: str, payload: dict[str, Any]) -> list[str]:
    """Every trigger name an event stands for (beats, replay rules)."""
    match event_type:
        case "state":
            return [state_trigger(str(payload.get("to")))]
        case "action" if payload.get("verb") == "restart":
            return [f"{payload.get('service')}.restarted"]
        case "deploy" if payload.get("ok"):
            return [f"{payload.get('service')}.deployed"]
        case "rollback" if payload.get("ok"):
            return [f"{payload.get('service')}.rolledback"]
        case "hint":
            return [f"hint:{payload.get('tier')}"]
        case "trail" if payload.get("verb") == "sql":
            return ["db.query"]
        case "message":
            return ["message"]
        case "mitigation":
            return ["mitigation.declared"]
        case "verify":
            return ["verify.passed" if payload.get("passed") else "verify.failed"]
        case _:
            return []


def event_text(event_type: str, payload: dict[str, Any]) -> str | None:
    """A one-line description of an event for the debrief, or None if it isn't shown there."""
    match event_type:
        case "alert":
            return f"Paged: {payload.get('title')}"
        case "action" if payload.get("verb") == "restart":
            return f"Restarted {payload.get('service')}"
        case "deploy":
            outcome = "" if payload.get("ok") else " (failed)"
            files = ", ".join(payload.get("files") or []) or "no changes"
            return f"Deployed {payload.get('service')} {payload.get('sha') or ''}{outcome}: {files}"
        case "rollback":
            outcome = "" if payload.get("ok") else " (failed)"
            ref = str(payload.get("sha") or payload.get("ref") or "")
            return f"Rolled {payload.get('service')} back to {ref[:7]}{outcome}"
        case "trail" if payload.get("verb") == "sql":
            return f"Queried the database: {payload.get('query')}"
        case "hint":
            return f"Took hint {payload.get('tier')}"
        case "message":
            return f"Posted an update: {payload.get('text')}"
        case "mitigation":
            agreed = "the metrics agreed" if payload.get("correct") else "the SLO still breached"
            return f"Declared it mitigated ({agreed})"
        case "state":
            return {
                "mitigated": "Recovered: the SLO held again",
                "active": f"Back to the incident: {payload['reason']}"
                if payload.get("reason")
                else None,
                "resolved": "Resolved: verify passed",
            }.get(str(payload.get("to")))
        case "verify":
            probes: list[dict[str, Any]] = list(payload.get("probes") or [])
            passed = sum(1 for p in probes if p.get("passed"))
            verdict = "passed" if payload.get("passed") else "failed"
            return f"Ran verify: {verdict} ({passed} of {len(probes)} checks)"
        case _:
            return None
