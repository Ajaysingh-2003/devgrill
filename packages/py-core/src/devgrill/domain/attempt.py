"""The attempt lifecycle: which state changes are allowed, and which states count as live.

The database enforces "one live attempt per user" with a partial unique index over
`LIVE_STATES`; this module is the single place that decides how an attempt may move.
"""

from __future__ import annotations

from typing import Final

from devgrill.domain.enums import AttemptState

S = AttemptState

#: States in which an attempt holds a sandbox (and blocks the user from starting another).
LIVE_STATES: Final = frozenset({S.PROVISIONING, S.ACTIVE, S.MITIGATED, S.VERIFYING})

#: States an attempt never leaves.
TERMINAL_STATES: Final = frozenset({S.RESOLVED, S.ABANDONED, S.EXPIRED, S.FAILED})

#: Every allowed move. Anything not listed is a bug in the caller.
TRANSITIONS: Final[dict[AttemptState, frozenset[AttemptState]]] = {
    # Sandbox comes up (or doesn't); the user may give up while waiting.
    S.PROVISIONING: frozenset({S.ACTIVE, S.FAILED, S.ABANDONED, S.EXPIRED}),
    # Investigating: declare mitigation, or go straight to verify with a fix.
    S.ACTIVE: frozenset({S.MITIGATED, S.VERIFYING, S.ABANDONED, S.EXPIRED, S.FAILED}),
    # Mitigated can regress (recovery didn't hold) or move on to verify.
    S.MITIGATED: frozenset({S.ACTIVE, S.VERIFYING, S.ABANDONED, S.EXPIRED, S.FAILED}),
    # Verify passes (resolved) or sends the user back to where they were.
    S.VERIFYING: frozenset({S.RESOLVED, S.ACTIVE, S.MITIGATED, S.EXPIRED, S.FAILED}),
    S.RESOLVED: frozenset(),
    S.ABANDONED: frozenset(),
    S.EXPIRED: frozenset(),
    S.FAILED: frozenset(),
}


class InvalidTransitionError(ValueError):
    """Raised when code asks an attempt to make a move the lifecycle doesn't allow."""

    def __init__(self, current: AttemptState, target: AttemptState) -> None:
        super().__init__(f"attempt cannot move from {current.value} to {target.value}")
        self.current = current
        self.target = target


def can_transition(current: AttemptState, target: AttemptState) -> bool:
    return target in TRANSITIONS[current]


def transition(current: AttemptState, target: AttemptState) -> AttemptState:
    """Return `target` if the move is allowed, else raise InvalidTransitionError."""
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
    return target


def is_live(state: AttemptState) -> bool:
    return state in LIVE_STATES
