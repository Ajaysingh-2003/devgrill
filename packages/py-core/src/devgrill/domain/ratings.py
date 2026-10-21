"""Rating updates for a finished attempt (ADR 015): one Glicko-2 game, player vs scenario.

The game's result is the attempt's incident score (devgrill.domain.scoring), so partial credit
is a partial result. Then:
  - the player's gain is scaled by mode: guided play counts half, tutorials don't count;
    losses are never scaled (hints already lower the score itself);
  - every change is bounded (MAX_DELTA), which keeps the sign Glicko-2 gives it;
  - the scenario is rated too, as having played the player with the opposite result.

Which attempts are rated at all is `rated()`: signed-in players, finished in a way that says
something about skill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from devgrill.domain import glicko2
from devgrill.domain.enums import AttemptMode, AttemptState
from devgrill.domain.glicko2 import Rating, Result

#: The most a single attempt moves a rating, either way (player and scenario).
MAX_DELTA: Final = 120.0
#: How much of a gain each mode keeps.
MODE_GAIN: Final[dict[AttemptMode, float]] = {
    AttemptMode.ONCALL: 1.0,
    AttemptMode.DAILY: 1.0,
    AttemptMode.WEEKLY: 1.0,
    AttemptMode.GUIDED: 0.5,
    AttemptMode.TUTORIAL: 0.0,
}
#: Leaving within this long, without ever running verify, is "wrong scenario", not a loss.
GRACE_SECONDS: Final = 180.0


@dataclass(frozen=True, slots=True)
class RatingChange:
    player_before: Rating
    player_after: Rating
    scenario_before: Rating
    scenario_after: Rating
    #: The expected result before the game, for the debrief ("you were expected to score 0.42").
    expected: float

    @property
    def delta(self) -> float:
        return self.player_after.rating - self.player_before.rating


def rated(
    *,
    signed_in: bool,
    mode: AttemptMode,
    state: AttemptState,
    active_seconds: float,
    verify_runs: int,
) -> bool:
    """Whether an attempt that just ended changes ratings."""
    if not signed_in or MODE_GAIN.get(mode, 0.0) == 0.0:
        return False
    if state is AttemptState.RESOLVED or state is AttemptState.EXPIRED:
        return True
    if state is AttemptState.ABANDONED:
        return verify_runs > 0 or active_seconds >= GRACE_SECONDS
    return False  # failed (our side), or not finished


def _bounded(before: Rating, after: Rating, scale: float = 1.0) -> Rating:
    # Bound first, then scale: a guided gain is exactly half the on-call one.
    delta = max(-MAX_DELTA, min(MAX_DELTA, after.rating - before.rating))
    if delta > 0:
        delta *= scale
    return Rating(before.rating + delta, after.rd, after.vol)


def rate_attempt(
    player: Rating, scenario: Rating, outcome: float, mode: AttemptMode
) -> RatingChange:
    """The ratings after one attempt with `outcome` in [0, 1]."""
    if not 0.0 <= outcome <= 1.0:
        raise ValueError("outcome must be between 0 and 1")
    player_new = glicko2.rate(player, [Result(scenario, outcome)])
    scenario_new = glicko2.rate(scenario, [Result(player, 1.0 - outcome)])
    return RatingChange(
        player_before=player,
        player_after=_bounded(player, player_new, MODE_GAIN.get(mode, 0.0)),
        scenario_before=scenario,
        scenario_after=_bounded(scenario, scenario_new),
        expected=glicko2.expected_score(player, scenario),
    )


def as_dict(r: Rating) -> dict[str, float]:
    return {"rating": round(r.rating, 2), "rd": round(r.rd, 2), "vol": round(r.vol, 6)}
