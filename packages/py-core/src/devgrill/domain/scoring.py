"""What an attempt earned (ADR 015): verify probes, the score's components, and the total.

The score combines a scenario's `scoring` weights:
  mitigation_time  first mitigation vs the scenario's par time (full credit up to par)
  resolution       the weighted share of probes the best verify run passed (partial credit)
  communication    status updates posted in the war room (counted)
  postmortem       the AI review's grade (ADR 016); pending, and left out, until it lands
and subtracts a penalty per hint taken. The **incident score** (everything but the
postmortem, renormalised) is what ratings use, so a later postmortem grade never moves a rating.

Pure functions, property-tested: the score never rises with a slower mitigation or with more
hints, and it always stays in [0, 1].
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from devgrill.domain.enums import ProbeKind

#: Each hint taken lowers the incident score by this much (never below zero).
HINT_PENALTY: Final = 0.1
#: Mitigation-time credit falls linearly from 1 at par to this floor at FLOOR_AT_PAR x par.
MITIGATION_FLOOR: Final = 0.25
FLOOR_AT_PAR: Final = 3.0
#: Status updates for full communication credit, and the credit for the first one alone.
UPDATES_FOR_FULL: Final = 2
FIRST_UPDATE_CREDIT: Final = 0.6


@dataclass(frozen=True, slots=True)
class Probe:
    """One behaviour verify checks, e.g. "p99 under 500 ms during a 10x replay"."""

    key: str
    kind: ProbeKind
    weight: float = 1.0

    def __post_init__(self) -> None:
        if self.weight <= 0:
            raise ValueError("probe weight must be positive")


@dataclass(frozen=True, slots=True)
class ProbeOutcome:
    probe: Probe
    passed: bool


def verify_score(outcomes: Sequence[ProbeOutcome]) -> float:
    """Weighted share of passing probes. No probes means nothing was verified: 0."""
    total = sum(o.probe.weight for o in outcomes)
    if total == 0:
        return 0.0
    return sum(o.probe.weight for o in outcomes if o.passed) / total


@dataclass(frozen=True, slots=True)
class Weights:
    mitigation_time: float = 0.25
    resolution: float = 0.4
    postmortem: float = 0.25
    communication: float = 0.1


@dataclass(frozen=True, slots=True)
class ScoreInput:
    weights: Weights
    par_minutes: float
    #: Minutes from the page to the first detected mitigation; None if it never happened.
    mitigation_minutes: float | None
    #: Weighted share of probes passed by the best verify run (0 without a run).
    resolution: float
    #: The best verify run held the SLO under replay and chaos (every load and chaos probe
    #: passed). Mitigation is detected from the app's own metrics during play, so it only
    #: earns credit once the verifier has measured the same thing from outside (ADR 015).
    slo_held_under_verify: bool
    hints_used: int = 0
    status_updates: int = 0
    #: 0..1 once graded (phase 6).
    postmortem: float | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.resolution <= 1.0:
            raise ValueError("resolution must be between 0 and 1")
        if self.par_minutes <= 0:
            raise ValueError("par must be positive")
        if self.hints_used < 0 or self.status_updates < 0:
            raise ValueError("counts cannot be negative")
        if self.mitigation_minutes is not None and self.mitigation_minutes < 0:
            raise ValueError("mitigation time cannot be negative")
        if self.postmortem is not None and not 0.0 <= self.postmortem <= 1.0:
            raise ValueError("postmortem must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Score:
    mitigation_time: float
    resolution: float
    communication: float
    postmortem: float | None
    hints_penalty: float
    #: Everything but the postmortem, renormalised, minus hints: what ratings use.
    incident: float
    #: Including the postmortem once it is graded (phase 6); None until then.
    total: float | None

    @property
    def resolved(self) -> bool:
        return self.resolution == 1.0


def mitigation_credit(minutes: float | None, par: float) -> float:
    """1 up to par, falling linearly to MITIGATION_FLOOR at FLOOR_AT_PAR x par; 0 if never."""
    if minutes is None:
        return 0.0
    if minutes <= par:
        return 1.0
    over = min(1.0, (minutes - par) / ((FLOOR_AT_PAR - 1.0) * par))
    return 1.0 - over * (1.0 - MITIGATION_FLOOR)


def communication_credit(updates: int) -> float:
    if updates <= 0:
        return 0.0
    return 1.0 if updates >= UPDATES_FOR_FULL else FIRST_UPDATE_CREDIT


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def score(inp: ScoreInput) -> Score:
    w = inp.weights
    mitigation = (
        mitigation_credit(inp.mitigation_minutes, inp.par_minutes)
        if inp.slo_held_under_verify
        else 0.0
    )
    communication = communication_credit(inp.status_updates)
    penalty = HINT_PENALTY * inp.hints_used

    parts = w.mitigation_time + w.resolution + w.communication
    weighted = (
        w.mitigation_time * mitigation
        + w.resolution * inp.resolution
        + w.communication * communication
    )
    incident = _clamp((weighted / parts if parts > 0 else inp.resolution) - penalty)
    total = (
        _clamp(weighted + w.postmortem * inp.postmortem - penalty)
        if inp.postmortem is not None
        else None
    )
    return Score(
        mitigation_time=round(mitigation, 4),
        resolution=round(inp.resolution, 4),
        communication=round(communication, 4),
        postmortem=inp.postmortem,
        hints_penalty=round(penalty, 4),
        incident=round(incident, 4),
        total=round(total, 4) if total is not None else None,
    )


def with_postmortem(stored: Mapping[str, Any], postmortem: float) -> dict[str, Any]:
    """A settled score (as stored on the attempt) once its postmortem is graded: `postmortem`
    and `total` are filled in. The incident score, and so the rating, stays as it was."""
    if not 0.0 <= postmortem <= 1.0:
        raise ValueError("postmortem must be between 0 and 1")
    w = stored["weights"]
    weighted = (
        w["mitigation_time"] * stored["mitigation_time"]
        + w["resolution"] * stored["resolution"]
        + w["communication"] * stored["communication"]
    )
    total = _clamp(weighted + w["postmortem"] * postmortem - stored["hints_penalty"])
    return {**stored, "postmortem": round(postmortem, 4), "total": round(total, 4)}
