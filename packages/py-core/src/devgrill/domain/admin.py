"""Who may do what in the content console (phase 7 gate: authors can't publish, reviewers can't
edit content, every action is audit-logged), and the scenario lifecycle (PLAN §11.4):

    draft ──submit──▶ review ──publish──▶ published ──retire──▶ retired
      ▲                 │                     ▲                   │
      └───send back─────┘                     └──────restore──────┘

Content itself is edited in git (`content/`), so "editing" in the console means moving a
draft into review: an author's step. Reviewers decide (send back, publish, retire); admins
can do everything, and alone manage users and roles.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from devgrill.domain.enums import Role, ScenarioStatus


class Permission(StrEnum):
    VIEW_CONSOLE = "view_console"
    SUBMIT = "submit"
    DECIDE = "decide"
    REVIEW_FIXES = "review_fixes"
    VIEW_COSTS = "view_costs"
    MANAGE_USERS = "manage_users"
    VIEW_AUDIT = "view_audit"


GRANTS: Final[dict[Role, frozenset[Permission]]] = {
    Role.USER: frozenset(),
    Role.AUTHOR: frozenset({Permission.VIEW_CONSOLE, Permission.SUBMIT}),
    Role.REVIEWER: frozenset({Permission.VIEW_CONSOLE, Permission.DECIDE, Permission.REVIEW_FIXES}),
    Role.ADMIN: frozenset(Permission),
}


def allowed(roles: Iterable[str], permission: Permission) -> bool:
    return any(permission in GRANTS.get(Role(r), frozenset()) for r in roles if r in Role)


class Action(StrEnum):
    SUBMIT = "submit"
    SEND_BACK = "send_back"
    PUBLISH = "publish"
    RETIRE = "retire"
    RESTORE = "restore"


@dataclass(frozen=True, slots=True)
class Transition:
    source: ScenarioStatus
    target: ScenarioStatus
    needs: Permission


TRANSITIONS: Final[dict[Action, Transition]] = {
    Action.SUBMIT: Transition(ScenarioStatus.DRAFT, ScenarioStatus.REVIEW, Permission.SUBMIT),
    Action.SEND_BACK: Transition(ScenarioStatus.REVIEW, ScenarioStatus.DRAFT, Permission.DECIDE),
    Action.PUBLISH: Transition(ScenarioStatus.REVIEW, ScenarioStatus.PUBLISHED, Permission.DECIDE),
    Action.RETIRE: Transition(ScenarioStatus.PUBLISHED, ScenarioStatus.RETIRED, Permission.DECIDE),
    Action.RESTORE: Transition(ScenarioStatus.RETIRED, ScenarioStatus.PUBLISHED, Permission.DECIDE),
}


def actions_for(roles: Iterable[str], status: ScenarioStatus) -> list[Action]:
    """What these roles can do to a scenario in `status` (for the console's buttons)."""
    held = list(roles)
    return [
        action for action, t in TRANSITIONS.items() if t.source is status and allowed(held, t.needs)
    ]


# ------------------------------------------------------------------------- analytics flags

#: Below this many finished attempts, rates say nothing: no flags.
MIN_ATTEMPTS: Final = 10


def flags(
    *,
    attempts: int,
    solve_rate: float,
    abandon_rate: float,
    median_minutes: float | None,
    est_minutes: int,
    hints_per_attempt: float,
) -> list[str]:
    """Automatic warnings for the analytics table (PLAN §11.4), in plain words."""
    if attempts < MIN_ATTEMPTS:
        return []
    out: list[str] = []
    if solve_rate < 0.10:
        out.append("Solve rate under 10%")
    if median_minutes is not None and median_minutes > 2 * est_minutes:
        out.append("Median time over twice the estimate")
    if abandon_rate > 0.5:
        out.append("Over half of players leave")
    if hints_per_attempt > 2.0:
        out.append("Most players need two or more hints")
    return out
