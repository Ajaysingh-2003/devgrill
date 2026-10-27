"""Wave 7D: on-call leave, Quick Fire counting toward the streak, the daily email and its pause."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from devgrill.infra import digests
from devgrill.infra.mail import MemoryMailer, pause_token, verify_pause_token
from devgrill.infra.models import ActivityDay, NotificationSent, Profile
from devgrill.infra.repositories import profiles

pytestmark = pytest.mark.integration

SECRET = "digest-test-secret"


def _today_ist() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(UTC).astimezone(ZoneInfo("Asia/Kolkata")).date()


def test_leave_is_booked_ahead_and_validated(api: TestClient, seeded: AsyncSession, auth) -> None:  # type: ignore[no-untyped-def]
    headers = auth(uuid.uuid4(), login="leaver")
    today = _today_ist()
    days = [str(today + timedelta(days=i)) for i in (1, 2, 3)]
    booked = api.put("/v1/me/leave", json={"days": days}, headers=headers)
    assert booked.status_code == 200
    assert booked.json()["days"] == days
    assert api.get("/v1/me/leave", headers=headers).json()["days"] == days
    # Replacing keeps only the new set.
    api.put("/v1/me/leave", json={"days": days[:1]}, headers=headers)
    assert api.get("/v1/me/leave", headers=headers).json()["days"] == days[:1]
    # Not in the past (a missed day can't be excused after the fact), not too far ahead.
    past = api.put("/v1/me/leave", json={"days": [str(today - timedelta(days=1))]}, headers=headers)
    assert past.json()["code"] == "leave_out_of_range"
    far = api.put(
        "/v1/me/leave", json={"days": [str(today + timedelta(days=200))]}, headers=headers
    )
    assert far.json()["code"] == "leave_out_of_range"
    # The streak shows booked leave too (the activity grid marks it).
    assert api.get("/v1/me/streak", headers=headers).json()["leave_days"] == days[:1]


async def test_a_quickfire_answer_counts_toward_the_streak(
    api: TestClient, seeded: AsyncSession, auth
) -> None:  # type: ignore[no-untyped-def]
    user = uuid.uuid4()
    headers = auth(user, login="quick")
    api.get("/v1/me", headers=headers)
    card = api.get("/v1/quickfire/deck", params={"limit": 1}).json()["cards"][0]
    api.post(f"/v1/quickfire/cards/{card['id']}/answer", json={"choice": "a"}, headers=headers)
    api.post(f"/v1/quickfire/cards/{card['id']}/answer", json={"choice": "b"}, headers=headers)
    rows = (
        (await seeded.execute(select(ActivityDay.kinds).where(ActivityDay.user_id == user)))
        .scalars()
        .all()
    )
    assert rows == [["quickfire"]]
    assert api.get("/v1/me/streak", headers=headers).json()["current"] == 1
    # Anonymous answers record nothing.
    api.post(f"/v1/quickfire/cards/{card['id']}/answer", json={"choice": "a"})
    assert await seeded.scalar(select(func.count()).select_from(ActivityDay)) == 1


def test_pause_tokens_are_signed_per_user() -> None:
    user = uuid.uuid4()
    token = pause_token(user, SECRET)
    assert verify_pause_token(token, SECRET) == user
    assert verify_pause_token(token, "another-secret") is None
    assert (
        verify_pause_token(
            pause_token(uuid.uuid4(), SECRET).split(".")[0] + "." + token.split(".")[1], SECRET
        )
        is None
    )
    assert verify_pause_token("junk", SECRET) is None


def test_one_tap_pause_turns_the_email_off(api: TestClient, seeded: AsyncSession, auth) -> None:  # type: ignore[no-untyped-def]
    user = uuid.uuid4()
    headers = auth(user, login="reader")
    on = api.patch(
        "/v1/me", json={"prefs": {"email_digest": True, "digest_hour": 18}}, headers=headers
    )
    assert on.json()["prefs"]["email_digest"] is True
    secret = api.app.state.settings.internal_hmac_secret  # type: ignore[attr-defined]
    paused = api.post("/v1/emails/pause", params={"token": pause_token(user, secret)})
    assert paused.json() == {"paused": True}
    assert api.get("/v1/me", headers=headers).json()["prefs"]["email_digest"] is False
    bad = api.post("/v1/emails/pause", params={"token": f"{user}.forged"})
    assert bad.json()["code"] == "invalid_token"
    # Send hours are a fixed set, outside quiet hours.
    assert (
        api.patch("/v1/me", json={"prefs": {"digest_hour": 23}}, headers=headers).status_code == 422
    )


async def _player(session: AsyncSession, *, email: str | None, **prefs: object) -> uuid.UUID:
    user = uuid.uuid4()
    await profiles.ensure(
        session, profiles.Identity(user_id=user, login=f"p{user.hex[:6]}", email=email)
    )
    profile = await session.get(Profile, user)
    assert profile is not None
    profile.prefs = {"email_digest": True, "digest_hour": 9, **prefs}
    await session.commit()
    return user


async def test_the_daily_email_goes_out_once_in_its_hour(
    db_engine: AsyncEngine, seeded: AsyncSession
) -> None:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    links = digests.Links(site="http://devgrill.test", secret=SECRET)
    keen = await _player(seeded, email="keen@example.com")
    await _player(seeded, email="off@example.com", email_digest=False)
    await _player(seeded, email=None)  # GitHub kept it private
    await _player(seeded, email="late@example.com", digest_hour=18)

    mailer = MemoryMailer()
    morning = datetime(2026, 10, 27, 4, 5, tzinfo=UTC)  # 09:35 IST
    assert await digests.send_due(factory, mailer, links, morning) == 1
    assert [m.to for m in mailer.sent] == ["keen@example.com"]
    mail = mailer.sent[0]
    assert mail.subject.startswith("Today's drill: ")
    assert f"/emails/pause?token={pause_token(keen, SECRET)}" in mail.text
    assert mail.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "—" not in mail.text  # voice: no em dashes

    # The next hourly sweep (and a retry of this one) sends nothing more today.
    assert await digests.send_due(factory, mailer, links, morning) == 0
    assert await digests.send_due(factory, mailer, links, morning + timedelta(hours=1)) == 0
    # Quiet hours: 23:05 IST sends nothing, even to the 18:00 player who hasn't had theirs.
    night = datetime(2026, 10, 27, 17, 35, tzinfo=UTC)
    assert await digests.send_due(factory, mailer, links, night) == 0
    evening = datetime(2026, 10, 27, 12, 35, tzinfo=UTC)  # 18:05 IST
    assert await digests.send_due(factory, mailer, links, evening) == 1
    assert mailer.sent[-1].to == "late@example.com"
    # Next morning, a new day.
    assert await digests.send_due(factory, mailer, links, morning + timedelta(days=1)) == 1
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(NotificationSent)) == 3
