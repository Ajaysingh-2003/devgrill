"""The signed-in user: profile, preferences, progress, streak, history; guest tokens."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from devgrill.domain.enums import StreakMode
from devgrill.domain.streaks import DEFAULT_TIMEZONE
from devgrill.infra.models import Profile
from devgrill.infra.repositories import catalog, profiles, progress
from devgrill_api import pagination
from devgrill_api.auth import guest
from devgrill_api.deps import SessionDep, SettingsDep, User, guest_ttl
from devgrill_api.errors import AppError
from devgrill_api.ratelimit import rate_limit
from devgrill_api.schemas import (
    AttemptPage,
    AttemptSummary,
    ClaimGuestIn,
    ClaimGuestOut,
    GuestTokenOut,
    Me,
    MePatch,
    Prefs,
    PublicProfile,
    RatingPoint,
    StreakOut,
    TopicProgress,
    TrackProgressDetail,
    TrackRating,
)

router = APIRouter(tags=["me"])

#: Days shown in the profile's activity grid.
HEATMAP_DAYS = 84


def _prefs(profile: Profile) -> Prefs:
    # Stored prefs may predate a field or contain stale values: fall back per field.
    defaults = Prefs()
    merged = {
        **defaults.model_dump(),
        **{k: v for k, v in profile.prefs.items() if k in Prefs.model_fields},
    }
    try:
        return Prefs.model_validate(merged)
    except ValueError:
        return defaults


def _me(profile: Profile) -> Me:
    return Me(
        user_id=profile.user_id,
        handle=profile.handle,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        country=profile.country,
        experience_level=profile.experience_level,
        roles=profile.roles,
        prefs=_prefs(profile),
        is_public=profile.is_public,
        created_at=profile.created_at,
    )


@router.get("/me", response_model=Me)
async def get_me(user: User) -> Me:
    return _me(user.profile)


@router.patch("/me", response_model=Me)
async def patch_me(body: MePatch, user: User, session: SessionDep) -> Me:
    """Update profile fields and merge preference changes (omitted fields are kept)."""
    profile = user.profile
    changes = body.model_dump(exclude_unset=True, exclude={"prefs"})
    for field, value in changes.items():
        setattr(profile, field, value)
    if body.prefs is not None:
        # Zones are validated by the schema (enum). A null value resets that pref to default.
        patch = body.prefs.model_dump(exclude_unset=True, mode="json")
        profile.prefs = profiles.merged_prefs(profile.prefs, patch)
    await session.flush()
    await session.refresh(profile)
    return _me(profile)


async def _ratings(session: SessionDep, user_id: uuid.UUID) -> list[TrackRating]:
    return [
        TrackRating(
            track_slug=track.slug,
            track_title=track.title,
            rating=rating.rating,
            rd=rating.rd,
            games=rating.games,
            history=[RatingPoint(ts=ts, rating=r) for ts, r in history],
        )
        for track, rating, history in await progress.ratings_with_history(session, user_id)
    ]


@router.get("/me/ratings", response_model=list[TrackRating])
async def my_ratings(user: User, session: SessionDep) -> list[TrackRating]:
    """Per-track Glicko-2 rating with recent history (tracks played at least once)."""
    return await _ratings(session, user.id)


@router.get("/me/progress", response_model=list[TrackProgressDetail])
async def my_progress(user: User, session: SessionDep) -> list[TrackProgressDetail]:
    """Solved and attempted counts and mastery per track and topic."""
    by_track = await catalog.track_progress(session, user.id)
    grouped: dict[uuid.UUID, TrackProgressDetail] = {}
    for track, topic, solved, total in await catalog.topic_progress(session, user.id):
        entry = grouped.get(track.id)
        if entry is None:
            p = by_track.get(track.id)
            entry = TrackProgressDetail(
                track_slug=track.slug,
                track_title=track.title,
                solved=p.solved if p else 0,
                attempted=p.attempted if p else 0,
                total=0,
                mastery_pct=0,
                topics=[],
            )
            grouped[track.id] = entry
        entry.total += total
        entry.topics.append(
            TopicProgress(
                slug=topic.slug if topic else "other",
                title=topic.title if topic else "Other",
                solved=solved,
                total=total,
            )
        )
    for entry in grouped.values():
        entry.mastery_pct = round(100 * entry.solved / entry.total) if entry.total else 0
    return list(grouped.values())


@router.get("/me/streak", response_model=StreakOut)
async def my_streak(user: User, session: SessionDep) -> StreakOut:
    """Current and longest streak (recomputed from activity days) and the activity grid."""
    prefs = _prefs(user.profile)
    tz = prefs.timezone or DEFAULT_TIMEZONE
    today = datetime.now(UTC).astimezone(ZoneInfo(tz)).date()
    streak = await progress.refresh_streak(
        session, user.id, today=today, mode=StreakMode(prefs.streak_mode)
    )
    since = today - timedelta(days=HEATMAP_DAYS - 1)
    return StreakOut(
        mode=streak.mode,
        current=streak.current,
        longest=streak.longest,
        freezes=streak.freezes,
        last_day=streak.last_day,
        days=await progress.activity_days(session, user.id, since),
        window_start=since,
    )


@router.get("/me/attempts", response_model=AttemptPage)
async def my_attempts(
    user: User,
    session: SessionDep,
    cursor: pagination.Cursor = None,
    limit: pagination.Limit = 20,
) -> AttemptPage:
    """Attempt history, newest first."""
    before = None
    if cursor:
        raw = pagination.decode(cursor)
        try:
            before = (datetime.fromisoformat(raw[0]), uuid.UUID(raw[1]))
        except (TypeError, ValueError, IndexError, KeyError) as exc:
            raise AppError(400, "invalid_cursor", "The cursor is not valid.") from exc
    rows = await progress.attempts(session, user.id, before=before, limit=limit + 1)
    page, more = rows[:limit], len(rows) > limit
    last = page[-1].attempt if page else None
    return AttemptPage(
        items=[
            AttemptSummary(
                id=r.attempt.id,
                track_slug=r.track_slug,
                scenario_slug=r.scenario_slug,
                scenario_title=r.scenario_title,
                difficulty=r.difficulty,
                mode=r.attempt.mode,
                state=r.attempt.state,
                started_at=r.attempt.started_at,
                ended_at=r.attempt.ended_at,
                score=(r.attempt.score or {}).get("incident"),
                rating_delta=(r.attempt.rating_delta or {}).get("delta"),
                mitigation_minutes=(r.attempt.score or {}).get("mitigation_minutes"),
            )
            for r in page
        ],
        next_cursor=pagination.encode([last.started_at.isoformat(), str(last.id)])
        if more and last
        else None,
    )


@router.post(
    "/me/claim-guest",
    response_model=ClaimGuestOut,
    dependencies=[Depends(rate_limit("claim-guest", limit=10, window_s=60))],
)
async def claim_guest(
    body: ClaimGuestIn, user: User, session: SessionDep, settings: SettingsDep
) -> ClaimGuestOut:
    """Attach attempts played as a guest to this account (after signing up)."""
    try:
        jti = guest.verify(body.guest_token, settings.guest_token_secret)
    except guest.GuestTokenError as exc:
        raise AppError(400, "invalid_guest_token", str(exc)) from exc
    claimed = await progress.claim_guest_attempts(session, user.id, guest.guest_hash(jti))
    return ClaimGuestOut(claimed=claimed)


@router.post(
    "/guest-tokens",
    response_model=GuestTokenOut,
    status_code=201,
    dependencies=[Depends(rate_limit("guest-tokens", limit=10, window_s=3600))],
)
async def create_guest_token(settings: SettingsDep) -> GuestTokenOut:
    """A signed token for playing /try without an account. Keep it in an httpOnly cookie."""
    try:
        issued = guest.issue(settings.guest_token_secret, guest_ttl(settings))
    except guest.GuestTokenError as exc:
        raise AppError(503, "guest_tokens_disabled", str(exc)) from exc
    return GuestTokenOut(token=issued.token, expires_at=issued.expires_at)


@router.get("/users/{handle}", response_model=PublicProfile, tags=["profiles"])
async def public_profile(handle: pagination.HandlePath, session: SessionDep) -> PublicProfile:
    """A player's public profile (404 when private, so private handles can't be probed)."""
    profile = await profiles.get_by_handle(session, handle)
    if profile is None or not profile.is_public:
        raise AppError(404, "user_not_found", f"No public profile for {handle!r}.")
    return PublicProfile(
        handle=profile.handle,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        created_at=profile.created_at,
        resolved=await progress.resolved_count(session, profile.user_id),
        ratings=await _ratings(session, profile.user_id),
    )
