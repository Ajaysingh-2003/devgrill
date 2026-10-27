"""Onboarding calibration (PLAN §8.3, phase 7): a starting rating per track, held loosely.

A new player says how long they've been doing this and may answer up to one Quick Fire card per
track. Each track then starts from the experience's base rating, a step up for a right answer
and a step down for a wrong one, with a high rating deviation: the first real games move it a
long way. A track the player already has a rating for is never touched (calibration can't
undo, or inflate, what play has shown).
"""

from __future__ import annotations

from typing import Final

from devgrill.domain.enums import ExperienceLevel
from devgrill.domain.glicko2 import DEFAULT_RATING, Rating

#: Where each experience level starts. Scenario ratings start at 1500 (a SEV3 is about even).
BASE: Final[dict[ExperienceLevel, float]] = {
    ExperienceLevel.STUDENT: 1350.0,
    ExperienceLevel.Y0_2: 1450.0,
    ExperienceLevel.Y2_5: 1550.0,
    ExperienceLevel.Y5_PLUS: 1650.0,
}
#: How far one calibration card moves a track's starting rating.
STEP: Final = 100.0
#: Deviation for a track the player answered a card for, and for one they didn't. Both are
#: below a stranger's 350 (we know something) and well above a settled player's (we know little).
RD_ANSWERED: Final = 300.0
RD_EXPERIENCE_ONLY: Final = 330.0
#: One card per track, at most.
MAX_CARDS: Final = 6


def starting_ratings(
    experience: ExperienceLevel | None,
    tracks: list[str],
    answers: dict[str, bool],
) -> dict[str, Rating]:
    """Starting ratings for `tracks` (slugs), from the experience and each track's card result."""
    base = BASE[experience] if experience is not None else DEFAULT_RATING
    out: dict[str, Rating] = {}
    for track in tracks:
        if track in answers:
            out[track] = Rating(base + (STEP if answers[track] else -STEP), RD_ANSWERED)
        else:
            out[track] = Rating(base, RD_EXPERIENCE_ONLY)
    return out
