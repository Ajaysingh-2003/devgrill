"""Quick Fire cards (no sandbox: free for everyone, ADR 013) and the onboarding calibration.

Cards go out without their answers; an answer is checked here and comes back with the
explanation. Onboarding records the player's experience and turns up to one calibration card
per track into starting ratings (devgrill.domain.calibration).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from devgrill.domain import calibration
from devgrill.infra.models import QuickfireCard, Track
from devgrill.infra.repositories import profiles
from devgrill.infra.repositories import quickfire as repo
from devgrill_api import pagination
from devgrill_api.deps import SessionDep, User
from devgrill_api.errors import AppError
from devgrill_api.ratelimit import rate_limit
from devgrill_api.routers.me import _me
from devgrill_api.schemas import (
    OnboardingIn,
    OnboardingOut,
    QuickfireAnswerIn,
    QuickfireAnswerOut,
    QuickfireCardOut,
    QuickfireDeck,
    QuickfireOptionOut,
)

router = APIRouter(tags=["quickfire"])


def _card(card: QuickfireCard, track: Track) -> QuickfireCardOut:
    return QuickfireCardOut(
        id=card.id,
        track_slug=track.slug,
        track_title=track.title,
        kind=card.kind,
        prompt=str(card.prompt["text"]),
        evidence=[str(line) for line in card.prompt.get("evidence", [])],
        options=[QuickfireOptionOut(key=o["key"], text=o["text"]) for o in card.options],
    )


def _result(card: QuickfireCard, choice: str) -> QuickfireAnswerOut:
    return QuickfireAnswerOut(
        card_id=card.id,
        correct=choice == card.answer,
        answer=card.answer,
        explanation_md=card.explanation_md,
    )


@router.get("/quickfire/deck", response_model=QuickfireDeck)
async def quickfire_deck(
    session: SessionDep,
    response: Response,
    track: pagination.SlugQuery = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> QuickfireDeck:
    """Random cards for a run, from one track or all of them. Answers are checked one by one."""
    response.headers["Cache-Control"] = "no-store"
    rows = await repo.deck(session, track_slug=track, limit=limit)
    return QuickfireDeck(cards=[_card(c, t) for c, t in rows])


@router.post(
    "/quickfire/cards/{card_id}/answer",
    response_model=QuickfireAnswerOut,
    dependencies=[Depends(rate_limit("quickfire-answer", limit=120, window_s=60))],
)
async def answer_card(
    card_id: uuid.UUID, body: QuickfireAnswerIn, session: SessionDep
) -> QuickfireAnswerOut:
    """Whether `choice` is right, with the answer and why."""
    found = (await repo.cards_by_id(session, [card_id])).get(card_id)
    if found is None:
        raise AppError(404, "card_not_found", "There's no such card.")
    return _result(found[0], body.choice)


@router.get("/onboarding/calibration", response_model=QuickfireDeck)
async def calibration_deck(user: User, session: SessionDep, response: Response) -> QuickfireDeck:
    """One card per track for the optional calibration (skippable)."""
    response.headers["Cache-Control"] = "no-store"
    return QuickfireDeck(cards=[_card(c, t) for c, t in await repo.calibration_deck(session)])


@router.post(
    "/me/onboarding",
    response_model=OnboardingOut,
    dependencies=[Depends(rate_limit("onboarding", limit=10, window_s=3600))],
)
async def finish_onboarding(body: OnboardingIn, user: User, session: SessionDep) -> OnboardingOut:
    """Save experience and role, check the calibration answers, seed starting ratings."""
    found = await repo.cards_by_id(session, [a.card_id for a in body.answers])
    results = []
    by_track: dict[str, bool] = {}
    for a in body.answers:
        if a.card_id not in found:
            raise AppError(422, "card_not_found", "One of the answered cards doesn't exist.")
        card, track = found[a.card_id]
        result = _result(card, a.choice)
        results.append(result)
        by_track.setdefault(track.slug, result.correct)  # the first card per track counts

    tracks = await repo.published_tracks(session)
    starting = calibration.starting_ratings(
        body.experience_level, [t.slug for t in tracks], by_track
    )
    ids = {t.slug: t.id for t in tracks}
    seeded = await repo.seed_ratings(
        session, user.id, {ids[slug]: r for slug, r in starting.items()}
    )

    profile = user.profile
    profile.experience_level = body.experience_level
    profile.prefs = profiles.merged_prefs(
        profile.prefs, {"onboarded": True, "job_role": body.job_role}
    )
    await session.flush()
    await session.refresh(profile)
    return OnboardingOut(
        me=_me(profile),
        results=results,
        seeded_tracks=[t.slug for t in tracks if t.id in set(seeded)],
    )
