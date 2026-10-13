"""Verify probes and the score an attempt earns from them.

Phase 2 defines the value objects and the mapping from probe results to a Glicko-2 game
score; phase 5 adds timing and postmortem components to the debrief.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from devgrill.domain.enums import ProbeKind

#: Each hint taken lowers the rating score by this much (never below zero).
HINT_PENALTY: Final = 0.1


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


@dataclass(frozen=True, slots=True)
class Score:
    """What an attempt earned. `verify` is the weighted share of probes that passed."""

    verify: float
    hints_used: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.verify <= 1.0:
            raise ValueError("verify score must be between 0 and 1")
        if self.hints_used < 0:
            raise ValueError("hints_used cannot be negative")

    @property
    def rating_score(self) -> float:
        """The game result fed to Glicko-2: verify share minus a per-hint penalty."""
        return max(0.0, self.verify - HINT_PENALTY * self.hints_used)

    @property
    def resolved(self) -> bool:
        return self.verify == 1.0


def verify_score(outcomes: Sequence[ProbeOutcome]) -> float:
    """Weighted share of passing probes. No probes means nothing was verified: 0."""
    total = sum(o.probe.weight for o in outcomes)
    if total == 0:
        return 0.0
    return sum(o.probe.weight for o in outcomes if o.passed) / total
