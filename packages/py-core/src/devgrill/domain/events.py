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
  deploy.viewed          the player looked at what a deploy changed
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
#: "review" is the postmortem review's bookkeeping (requested, graded, failed).
HIDDEN_TYPES: Final = frozenset({"fault", "health", "trail", "review"})

#: Shown in the incident timeline (the rest drive state, the boot sequence or the war room).
TIMELINE_TYPES: Final = frozenset(
    {
        "alert",
        "beat",
        "reply",
        "message",
        "nudge",
        "action",
        "deploy",
        "rollback",
        "hint",
        "mitigation",
        "state",
    }
)


#: Why a working service went back to the incident (the current text and the one before it).
REGRESSED_REASONS: Final = frozenset(
    {"the service went over its target again", "the SLO broke again"}
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
        case "trail" if payload.get("verb") == "diff":
            return ["deploy.viewed"]
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
        case "trail" if payload.get("verb") == "diff":
            return f"Looked at what deploy {payload.get('sha')} changed on {payload.get('service')}"
        case "hint":
            return f"Took hint {payload.get('tier')}"
        case "message":
            return f"Posted an update: {payload.get('text')}"
        case "mitigation":
            agreed = "the graphs agreed" if payload.get("correct") else "it was still over target"
            return f"Said it's working again ({agreed})"
        case "state":
            match payload.get("to"):
                case "mitigated":
                    return "Working again: the service met its target"
                case "active" if payload.get("reason") in REGRESSED_REASONS:
                    return "Over target again"
                case "active" if payload.get("reason") == "reset":
                    return "Started again from the broken system"
                case "active" if payload.get("reason"):
                    return f"Back to it: {payload['reason']}"
                case "resolved":
                    return "Fixed: every check passed"
                case _:
                    return None
        case "verify":
            probes: list[dict[str, Any]] = list(payload.get("probes") or [])
            passed = sum(1 for p in probes if p.get("passed"))
            verdict = "passed" if payload.get("passed") else "not fixed yet"
            return f"Checked the fix: {verdict} ({passed} of {len(probes)} checks)"
        case _:
            return None
