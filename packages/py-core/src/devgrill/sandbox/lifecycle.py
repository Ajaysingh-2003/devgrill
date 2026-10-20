"""The contract between the API and the SandboxLifecycle workflow (apps/worker).

Both sides import only this module: the workflow's name, its input, its signals and its
status query. The workflow id is derived from the attempt id, so the API never stores it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

WORKFLOW_NAME = "SandboxLifecycle"
SIGNAL_ABANDON = "abandon"
SIGNAL_RESET = "reset"
SIGNAL_EXTEND = "extend"
SIGNAL_VERIFY = "verify"
SIGNAL_TOUCH = "touch"
QUERY_STATUS = "status"

#: A reset rebuilds the sandbox from scratch; more than this in one attempt is refused.
MAX_RESETS = 3


def workflow_id(attempt_id: str) -> str:
    return f"attempt-{attempt_id}"


def events_channel(attempt_id: str) -> str:
    """Valkey pub/sub channel that announces new rows in attempt_events for an attempt."""
    return f"attempt:{attempt_id}:events"


@dataclass(slots=True)
class LifecycleInput:
    attempt_id: str
    scenario_slug: str
    #: guest | free | pro | team: recorded on the sandbox session for budget accounting.
    tier: str
    ttl_minutes: int
    idle_minutes: int
    extend_minutes: int = 0
    max_extends: int = 0


@dataclass(slots=True)
class LaterFault:
    """A fault due after T (load start), applied by the workflow's timer."""

    at_seconds: int
    use: str
    params: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class Provisioned:
    ref: str
    later_faults: list[LaterFault] = field(default_factory=list)


@dataclass(slots=True)
class LifecycleStatus:
    state: str
    expires_at: str | None
    extends_used: int
    resets_used: int
