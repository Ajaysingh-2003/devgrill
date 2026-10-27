"""The daily email (wave 7D): today's drill and your streak, for players who turned it on.

The worker's hourly sweep calls `send_due`. For each opted-in player whose digest is due
(devgrill.domain.digest), it first claims the day in `notifications_sent`; only a claim that
inserts goes on to send. A retried sweep, or two workers, can't send twice; a send that fails
after its claim is logged and skipped for that day (missing one beats repeating one).
"""

from __future__ import annotations

import html
import uuid
from dataclasses import dataclass
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from devgrill.domain import digest
from devgrill.domain.enums import ChallengeKind, StreakMode
from devgrill.domain.streaks import DEFAULT_TIMEZONE
from devgrill.infra.mail import Mail, Mailer, pause_token
from devgrill.infra.models import NotificationSent, Profile, Scenario, ScenarioVersion
from devgrill.infra.repositories import challenges, progress

log = structlog.get_logger(__name__)

KIND = "digest"


@dataclass(frozen=True, slots=True)
class Daily:
    title: str
    difficulty: str
    est_minutes: int


@dataclass(frozen=True, slots=True)
class Links:
    site: str
    secret: str


async def _daily(session: AsyncSession, now: datetime) -> Daily | None:
    current = await challenges.current(session, ChallengeKind.DAILY, now=now)
    if current is None:
        return None
    row = (
        await session.execute(
            select(Scenario.title, Scenario.difficulty, Scenario.est_minutes)
            .join(ScenarioVersion, ScenarioVersion.scenario_id == Scenario.id)
            .where(ScenarioVersion.id == current[0].scenario_version_id)
        )
    ).one()
    return Daily(title=row[0], difficulty=str(row[1]), est_minutes=row[2])


def compose(
    *,
    to: str,
    name: str,
    user_id: uuid.UUID,
    daily: Daily,
    streak: int,
    freezes: int,
    links: Links,
) -> Mail:
    """The email itself: plain words, no guilt (PLAN §8.5), a pause link in every one."""
    sev = daily.difficulty.upper()
    play = f"{links.site}/daily"
    token = pause_token(user_id, links.secret)
    pause = f"{links.site}/emails/pause?token={token}"
    lines = [
        f"Hi {name},",
        "",
        f"Today's drill is {daily.title} ({sev}, about {daily.est_minutes} minutes). "
        "It's the same for everyone and closes at midnight India time.",
    ]
    if streak > 0:
        saved = (
            f" You have {freezes} streak freeze{'s' if freezes != 1 else ''} saved."
            if freezes
            else ""
        )
        lines += ["", f"Your streak: {streak} {'day' if streak == 1 else 'days'}.{saved}"]
    lines += [
        "",
        f"Play it: {play}",
        "",
        f"You get this email because you turned it on in Settings. Pause it with one tap: {pause}",
    ]
    text = "\n".join(lines)
    paragraphs = "".join(
        f"<p>{html.escape(block).replace(chr(10), '<br>')}</p>"
        # The text before the links: one paragraph per blank-line-separated block.
        for block in "\n".join(lines[:-3]).strip().split("\n\n")
    )
    body = (
        f"{paragraphs}"
        f'<p><a href="{html.escape(play)}">Play today&#8217;s drill</a></p>'
        '<p style="color:#5f5c57;font-size:13px">You get this email because you turned it on '
        f'in Settings. <a href="{html.escape(pause)}">Pause it</a>.</p>'
    )
    return Mail(
        to=to,
        subject=f"Today's drill: {daily.title}",
        text=text,
        html=body,
        headers={
            "List-Unsubscribe": f"<{links.site}/api/emails/pause?token={token}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )


async def send_due(
    session_factory: async_sessionmaker[AsyncSession],
    mailer: Mailer,
    links: Links,
    now: datetime,
) -> int:
    """Send every digest due at `now`; returns how many went out."""
    async with session_factory() as session, session.begin():
        candidates = (
            await session.scalars(
                select(Profile).where(
                    Profile.email.is_not(None), Profile.prefs["email_digest"].as_boolean().is_(True)
                )
            )
        ).all()
        daily = await _daily(session, now)
    if daily is None:
        return 0

    sent = 0
    for profile in candidates:
        prefs = profile.prefs
        tz = str(prefs.get("timezone") or DEFAULT_TIMEZONE)
        hour = int(prefs.get("digest_hour") or digest.DEFAULT_SEND_HOUR)
        if not digest.due(now, enabled=True, timezone=tz, send_hour=hour, sent_today=False):
            continue
        day = digest.local_day(now, tz)
        async with session_factory() as session, session.begin():
            claimed = await session.scalar(
                insert(NotificationSent)
                .values(user_id=profile.user_id, kind=KIND, day=day)
                .on_conflict_do_nothing()
                .returning(NotificationSent.user_id)
            )
            if claimed is None:
                continue  # already sent today
            streak = await progress.refresh_streak(
                session,
                profile.user_id,
                today=day,
                mode=StreakMode(prefs.get("streak_mode") or StreakMode.DAILY),
            )
        assert profile.email is not None
        mail = compose(
            to=profile.email,
            name=profile.display_name,
            user_id=profile.user_id,
            daily=daily,
            streak=streak.current,
            freezes=streak.freezes,
            links=links,
        )
        try:
            await mailer.send(mail)
        except Exception:
            log.warning("digest_send_failed", user_id=str(profile.user_id), exc_info=True)
            continue
        sent += 1
    log.info("digests_sent", count=sent, candidates=len(candidates))
    return sent
