"""/v1 against a real, seeded Postgres and Valkey (`just deps-up`)."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import ApproachOutcome, AttemptMode, AttemptState, ChallengeKind
from devgrill.infra.models import Approach, Attempt, Scenario, ScenarioVersion
from devgrill_api.auth import guest, internal
from devgrill_content.seed import seed

pytestmark = pytest.mark.integration

CONTENT = Path(__file__).resolve().parents[3] / "content"
SECRET = "test-secret-" + "x" * 40


@pytest.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    await seed(db_session, CONTENT)
    await db_session.commit()
    return db_session


async def _attempt(
    session: AsyncSession,
    slug: str,
    *,
    user_id: uuid.UUID | None = None,
    guest_hash: str | None = None,
    state: AttemptState = AttemptState.RESOLVED,
) -> Attempt:
    scenario = (await session.execute(select(Scenario).where(Scenario.slug == slug))).scalar_one()
    attempt = Attempt(
        user_id=user_id,
        guest_token_hash=guest_hash,
        scenario_version_id=scenario.current_version_id,
        mode=AttemptMode.GUIDED,
        state=state,
    )
    session.add(attempt)
    await session.commit()
    return attempt


# ---------------------------------------------------------------------------- catalog


def test_tracks_are_public_and_cacheable(api: TestClient, seeded: AsyncSession) -> None:
    response = api.get("/v1/tracks")
    assert response.status_code == 200
    tracks = response.json()
    assert [t["slug"] for t in tracks][:2] == ["databases", "caching"]
    # Draft tracks (deploys, distributed) stay hidden.
    assert "deploys" not in {t["slug"] for t in tracks}
    caching = next(t for t in tracks if t["slug"] == "caching")
    assert caching["scenario_count"] == 6
    assert caching["progress"] is None
    assert response.headers["cache-control"].startswith("public")
    assert response.headers["ratelimit-policy"].startswith('"default"')


def test_track_detail_groups_by_topic_easiest_first(api: TestClient, seeded: AsyncSession) -> None:
    detail = api.get("/v1/tracks/caching").json()
    stampedes = next(t for t in detail["topics_detail"] if t["slug"] == "stampedes")
    assert stampedes["has_primer"] is True
    assert {s["slug"] for s in stampedes["scenarios"]} == {
        "big-sale-meltdown",
        "redis-restart-herd",
    }
    assert api.get("/v1/tracks/nope").json()["code"] == "track_not_found"


def test_scenarios_paginate_with_cursors(api: TestClient, seeded: AsyncSession) -> None:
    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 5, **({"cursor": cursor} if cursor else {})}
        page = api.get("/v1/scenarios", params=params).json()
        seen += [s["slug"] for s in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == 12 == len(set(seen))
    assert seen == sorted(seen)
    sev1 = api.get("/v1/scenarios", params={"difficulty": "sev1"}).json()["items"]
    assert {s["difficulty"] for s in sev1} == {"sev1"}
    found = api.get("/v1/scenarios", params={"q": "Stale"}).json()["items"]
    assert [s["slug"] for s in found] == ["stale-prices"]
    # Malformed cursors fail validation; well-formed ones we never issued are a 400.
    assert api.get("/v1/scenarios", params={"cursor": "!!"}).status_code == 422
    assert api.get("/v1/scenarios", params={"cursor": "AAAA"}).json()["code"] == "invalid_cursor"


def test_briefing_has_story_system_goals_and_no_solutions(
    api: TestClient, seeded: AsyncSession
) -> None:
    body = api.get("/v1/scenarios/big-sale-meltdown").json()
    assert body["briefing"]["story"].startswith("You are on call for ShopKart")
    assert body["briefing"]["system"][0]["name"] == "load-gen"
    # Authored goals win over the defaults.
    assert [g["title"] for g in body["briefing"]["goals"]] == [
        "Stop the bleeding",
        "Find what changed",
        "Make it hold",
    ]
    assert body["stats"]["solve_rate_pct"] is None  # too few attempts to show
    assert body["warmup"]["difficulty"] in {"sev4", "sev3"}
    assert "approaches" not in json.dumps(body)


async def test_approaches_are_only_for_players_who_resolved_it(
    api: TestClient, seeded: AsyncSession, auth
) -> None:  # type: ignore[no-untyped-def]
    scenario = (
        await seeded.execute(select(Scenario).where(Scenario.slug == "ttl-zero"))
    ).scalar_one()
    seeded.add(
        Approach(
            scenario_id=scenario.id,
            key="set-ttl",
            name="Set a real TTL",
            outcome=ApproachOutcome.FULL,
            idea_md="Configure the TTL",
        )
    )
    await seeded.commit()
    user = uuid.uuid4()
    url = "/v1/scenarios/ttl-zero/approaches"
    assert api.get(url).status_code == 401
    assert api.get(url, headers=auth(user)).json()["code"] == "not_resolved"
    await _attempt(seeded, "ttl-zero", user_id=user)
    # The seeded approaches (content/…/approaches) and the one added here.
    keys = [a["key"] for a in api.get(url, headers=auth(user)).json()]
    assert set(keys) == {"restore-ttl", "rollback", "set-ttl"}


def test_daily_challenge_is_stable(api: TestClient, seeded: AsyncSession) -> None:
    first = api.get("/v1/challenges/daily").json()
    second = api.get("/v1/challenges/daily").json()
    assert first == second
    assert first["kind"] == "daily"
    # IST window: starts at 18:30 UTC the previous day.
    assert first["starts_at"].endswith("18:30:00Z")


# ------------------------------------------------------------------------- me & auth


def test_me_requires_a_valid_token(api: TestClient, seeded: AsyncSession, signer, auth) -> None:  # type: ignore[no-untyped-def]
    assert api.get("/v1/me").status_code == 401
    assert api.get("/v1/me").headers["www-authenticate"].startswith("Bearer")
    expired = {"Authorization": f"Bearer {signer.token(exp_in=-120)}"}
    assert api.get("/v1/me", headers=expired).json()["code"] == "invalid_token"
    wrong_aud = {"Authorization": f"Bearer {signer.token(aud='other')}"}
    assert api.get("/v1/me", headers=wrong_aud).status_code == 401
    assert api.get("/v1/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_first_request_creates_the_profile(api: TestClient, seeded: AsyncSession, auth) -> None:  # type: ignore[no-untyped-def]
    user = uuid.uuid4()
    me = api.get("/v1/me", headers=auth(user, login="Ajay-Singh", name="Ajay")).json()
    assert me["user_id"] == str(user)
    assert me["handle"] == "Ajay-Singh"
    assert me["roles"] == ["user"]
    assert me["prefs"]["timezone"] == "Asia/Kolkata"
    # A second user with the same login gets a unique handle.
    other = api.get("/v1/me", headers=auth(uuid.uuid4(), login="ajay-singh")).json()
    assert other["handle"].lower() != "ajay-singh"
    assert other["handle"].lower().startswith("ajay-singh-")


def test_patch_me_merges_prefs(api: TestClient, seeded: AsyncSession, auth) -> None:  # type: ignore[no-untyped-def]
    headers = auth(uuid.uuid4(), login="pat")
    api.patch("/v1/me", json={"prefs": {"theme": "dark"}}, headers=headers)
    me = api.patch(
        "/v1/me", json={"display_name": "Pat", "prefs": {"pro_mode": True}}, headers=headers
    ).json()
    assert me["prefs"]["theme"] == "dark"
    assert me["prefs"]["pro_mode"] is True
    assert me["display_name"] == "Pat"
    bad = api.patch("/v1/me", json={"prefs": {"timezone": "Mars/Base"}}, headers=headers)
    assert bad.status_code == 422
    assert api.patch("/v1/me", json={"is_public": None}, headers=headers).status_code == 422
    assert api.patch("/v1/me", json={"country": "india"}, headers=headers).status_code == 422


async def test_progress_streak_and_history(api: TestClient, seeded: AsyncSession, auth) -> None:  # type: ignore[no-untyped-def]
    user = uuid.uuid4()
    headers = auth(user, login="prog")
    api.get("/v1/me", headers=headers)
    await _attempt(seeded, "ttl-zero", user_id=user)
    await _attempt(seeded, "stale-prices", user_id=user, state=AttemptState.ABANDONED)
    today = (
        await seeded.execute(text("SELECT (now() AT TIME ZONE 'Asia/Kolkata')::date"))
    ).scalar_one()
    await seeded.execute(
        text("INSERT INTO app.activity_days (user_id, day) VALUES (:u, :d), (:u, :d - 1)"),
        {"u": user, "d": today},
    )
    await seeded.commit()

    tracks = api.get("/v1/tracks", headers=headers).json()
    caching = next(t for t in tracks if t["slug"] == "caching")
    assert caching["progress"] == {"solved": 1, "attempted": 1, "mastery_pct": 17, "rating": None}
    assert api.get("/v1/tracks", headers=headers).headers["cache-control"].startswith("private")

    progress = api.get("/v1/me/progress", headers=headers).json()
    assert next(p for p in progress if p["track_slug"] == "caching")["solved"] == 1

    streak = api.get("/v1/me/streak", headers=headers).json()
    assert streak["current"] == 2
    assert len(streak["days"]) == 2

    page = api.get("/v1/me/attempts", params={"limit": 1}, headers=headers).json()
    assert len(page["items"]) == 1
    rest = api.get("/v1/me/attempts", params={"cursor": page["next_cursor"]}, headers=headers)
    assert len(rest.json()["items"]) == 1
    assert rest.json()["next_cursor"] is None

    card = api.get("/v1/tracks/caching", headers=headers).json()
    states = {s["slug"]: s["progress"] for t in card["topics_detail"] for s in t["scenarios"]}
    assert states["ttl-zero"] == "solved"
    assert states["stale-prices"] == "attempted"
    assert states["big-sale-meltdown"] == "new"


def test_public_profiles_respect_privacy(api: TestClient, seeded: AsyncSession, auth) -> None:  # type: ignore[no-untyped-def]
    headers = auth(uuid.uuid4(), login="shy")
    assert api.get("/v1/me", headers=headers).json()["is_public"] is False
    # Private by default (opt-in): hidden from everyone else, but the owner can see it.
    assert api.get("/v1/users/shy").json()["code"] == "user_not_found"
    assert api.get("/v1/users/shy", headers=auth(uuid.uuid4(), login="nosy")).status_code == 404
    assert api.get("/v1/users/shy", headers=headers).status_code == 200
    api.patch("/v1/me", json={"is_public": True}, headers=headers)
    assert api.get("/v1/users/shy").status_code == 200
    api.patch("/v1/me", json={"is_public": False}, headers=headers)
    assert api.get("/v1/users/shy").json()["code"] == "user_not_found"


# ------------------------------------------------------------------- guests & claim


async def test_guest_attempts_are_claimed_after_sign_up(
    api: TestClient, seeded: AsyncSession, auth
) -> None:  # type: ignore[no-untyped-def]
    issued = api.post("/v1/guest-tokens")
    assert issued.status_code == 201
    token = issued.json()["token"]
    jti = guest.verify(token, SECRET)
    await _attempt(seeded, "ttl-zero", guest_hash=guest.guest_hash(jti))
    await _attempt(
        seeded, "pool-party", guest_hash=guest.guest_hash(jti), state=AttemptState.ACTIVE
    )

    user = uuid.uuid4()
    headers = auth(user, login="newbie")
    claim = api.post("/v1/me/claim-guest", json={"guest_token": token}, headers=headers)
    assert claim.json() == {"claimed": 2}
    # Idempotent: nothing left to claim.
    again = api.post("/v1/me/claim-guest", json={"guest_token": token}, headers=headers)
    assert again.json() == {"claimed": 0}
    assert len(api.get("/v1/me/attempts", headers=headers).json()["items"]) == 2
    bad = api.post("/v1/me/claim-guest", json={"guest_token": "x" * 40}, headers=headers)
    assert bad.json()["code"] == "invalid_guest_token"


# --------------------------------------------------------------------------- authz


ADMIN_ROUTES = [
    ("GET", "/v1/admin/scenarios"),
    ("GET", "/v1/admin/ai/costs"),
    ("GET", "/v1/admin/approach-candidates"),
    ("POST", "/v1/admin/approach-candidates/{candidate_id}"),
]
#: What an admin gets with these test inputs (a random id is a 404).
ADMIN_OK = {"/v1/admin/approach-candidates/{candidate_id}": 404}
ADMIN_BODY = {"/v1/admin/approach-candidates/{candidate_id}": {"status": "dismissed"}}


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
def test_admin_routes_need_the_admin_role(
    api: TestClient, seeded: AsyncSession, auth, method: str, path: str
) -> None:  # type: ignore[no-untyped-def]
    url = path.replace("{candidate_id}", str(uuid.uuid4()))
    body = ADMIN_BODY.get(path)
    assert api.request(method, url, json=body).status_code == 401
    rando = auth(uuid.uuid4(), login="rando")
    assert api.request(method, url, json=body, headers=rando).status_code == 403
    # ADMIN_GITHUB_LOGINS=root-admin grants the role on first sign-in.
    admin = api.request(method, url, json=body, headers=auth(uuid.uuid4(), login="root-admin"))
    assert admin.status_code == ADMIN_OK.get(path, 200)


def test_operation_ids_are_unique_handler_names(api: TestClient) -> None:
    ids = [
        op["operationId"]
        for ops in api.get("/openapi.json").json()["paths"].values()
        for op in ops.values()
    ]
    assert len(ids) == len(set(ids))
    assert "list_tracks" in ids


def test_admin_route_list_is_complete(api: TestClient) -> None:
    """Every /v1/admin route must be in ADMIN_ROUTES so the authz test covers it."""
    schema = api.get("/openapi.json").json()
    admin = {
        (method.upper(), path)
        for path, ops in schema["paths"].items()
        if path.startswith("/v1/admin")
        for method in ops
    }
    assert admin == set(ADMIN_ROUTES)


def test_admin_scenarios_lists_every_status(api: TestClient, seeded: AsyncSession, auth) -> None:  # type: ignore[no-untyped-def]
    body = api.get("/v1/admin/scenarios", headers=auth(uuid.uuid4(), login="root-admin")).json()
    assert len(body["items"]) == 12
    assert all(item["version"] == 1 for item in body["items"])


# ------------------------------------------------------------------- internal hook


def _signed(
    body: dict[str, object], *, secret: str = SECRET, ts: int | None = None
) -> dict[str, object]:
    raw = json.dumps(body).encode()
    stamp = ts or int(time.time())
    return {
        "content": raw,
        "headers": {
            "content-type": "application/json",
            "x-devgrill-timestamp": str(stamp),
            "x-devgrill-signature": internal.sign(secret, stamp, raw),
        },
    }


def test_profile_hook_requires_a_valid_signature(api: TestClient, seeded: AsyncSession) -> None:
    user = str(uuid.uuid4())
    body = {"user_id": user, "login": "hooked", "name": "Hooked"}
    ok = api.post("/internal/profiles", **_signed(body))  # type: ignore[arg-type]
    assert ok.json() == {"user_id": user, "handle": "hooked", "created": True}
    again = api.post("/internal/profiles", **_signed(body))  # type: ignore[arg-type]
    assert again.json()["created"] is False
    forged = api.post("/internal/profiles", **_signed(body, secret="wrong"))  # type: ignore[arg-type]
    assert forged.status_code == 401
    stale = api.post("/internal/profiles", **_signed(body, ts=int(time.time()) - 900))  # type: ignore[arg-type]
    assert stale.json()["detail"] == "stale request"
    assert "/internal/profiles" not in api.get("/openapi.json").json()["paths"]


# -------------------------------------------------- rate limits, idempotency, CORS


def test_rate_limit_returns_429_with_retry_after(api_settings, signer, db_engine) -> None:  # type: ignore[no-untyped-def]
    from devgrill_api.auth.jwks import JwksCache
    from devgrill_api.main import create_app

    settings = api_settings.model_copy(update={"rate_limit_default": 3})
    app = create_app(settings)
    app.state.jwks = JwksCache(signer.fetch)
    with TestClient(app) as client:
        assert client.portal is not None
        client.portal.call(app.state.valkey.flushdb)
        codes = [client.get("/v1/tracks").status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
        limited = client.get("/v1/tracks")
        assert limited.json()["code"] == "rate_limited"
        assert int(limited.headers["retry-after"]) > 0


def test_guest_token_issuance_has_a_strict_bucket(api: TestClient, seeded: AsyncSession) -> None:
    codes = [api.post("/v1/guest-tokens").status_code for _ in range(11)]
    assert codes[:10] == [201] * 10
    assert codes[10] == 429


def test_idempotency_key_replays_the_first_response(api: TestClient, seeded: AsyncSession) -> None:
    key = {"Idempotency-Key": "guest-1"}
    first = api.post("/v1/guest-tokens", headers=key)
    replay = api.post("/v1/guest-tokens", headers=key)
    assert replay.status_code == first.status_code == 201
    assert replay.json() == first.json()
    assert replay.headers["idempotent-replayed"] == "true"
    reused = api.post("/v1/guest-tokens", headers=key, json={"different": True})
    assert reused.json()["code"] == "idempotency_key_reused"
    assert api.post("/v1/guest-tokens", headers={"Idempotency-Key": "bad key"}).status_code == 400


def test_cors_only_allows_the_web_origin(api: TestClient) -> None:
    preflight = {"Access-Control-Request-Method": "GET"}
    allowed = api.options("/v1/tracks", headers={"Origin": "http://localhost:3000", **preflight})
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in allowed.headers
    denied = api.options("/v1/tracks", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in denied.headers


async def test_daily_rotation_only_has_playable_scenarios(seeded: AsyncSession) -> None:
    from sqlalchemy import select

    from devgrill.infra.models import Scenario
    from devgrill.infra.repositories import challenges

    versions = await challenges.rotation(seeded)
    slugs = set(
        (
            await seeded.scalars(
                select(Scenario.slug).where(Scenario.current_version_id.in_(versions))
            )
        ).all()
    )
    # Placeholders (playable: false) never become the Daily.
    assert slugs == {"ttl-zero", "pool-party", "big-sale-meltdown"}


async def test_share_card_is_public_and_spoiler_free(api: TestClient, seeded: AsyncSession) -> None:
    from datetime import UTC, datetime, timedelta

    from devgrill.domain.streaks import activity_day
    from devgrill.infra.repositories import challenges

    now = datetime.now(UTC)
    current = await challenges.current(seeded, ChallengeKind.DAILY, now=now)
    assert current is not None
    daily, _ = current
    slug = (
        await seeded.execute(
            select(Scenario.slug)
            .join(ScenarioVersion, ScenarioVersion.scenario_id == Scenario.id)
            .where(ScenarioVersion.id == daily.scenario_version_id)
        )
    ).scalar_one()
    attempt = await _attempt(seeded, slug, guest_hash="g")
    attempt.active_at = now - timedelta(minutes=11, seconds=42)
    attempt.resolved_at = now
    attempt.hints_used = 1
    await seeded.commit()

    card = api.get(f"/v1/share/{attempt.id}")
    assert card.status_code == 200
    body = card.json()
    assert body["resolved_in_s"] == 702
    assert body["hints_used"] == 1
    assert body["daily_on"] == activity_day(now).isoformat()
    # Nothing about the player, the cause or the fix.
    assert set(body) == {
        "scenario_title",
        "scenario_slug",
        "track_slug",
        "difficulty",
        "resolved_in_s",
        "hints_used",
        "daily_on",
    }
    # Unresolved attempts and unknown ids share nothing.
    open_attempt = await _attempt(seeded, slug, guest_hash="h", state=AttemptState.ACTIVE)
    assert api.get(f"/v1/share/{open_attempt.id}").json()["code"] == "share_not_found"
    assert api.get(f"/v1/share/{uuid.uuid4()}").status_code == 404


# ---------------------------------------------------------------------- Quick Fire and onboarding


def test_quickfire_deck_hides_answers_and_checks_them(
    api: TestClient, seeded: AsyncSession
) -> None:
    deck = api.get("/v1/quickfire/deck", params={"track": "caching", "limit": 5})
    assert deck.status_code == 200
    cards = deck.json()["cards"]
    assert len(cards) == 5
    assert {c["track_slug"] for c in cards} == {"caching"}
    assert all("answer" not in c and "explanation_md" not in c for c in cards)

    card = cards[0]
    results = [
        api.post(f"/v1/quickfire/cards/{card['id']}/answer", json={"choice": o["key"]}).json()
        for o in card["options"]
    ]
    assert sum(r["correct"] for r in results) == 1
    assert len({r["answer"] for r in results}) == 1
    assert results[0]["explanation_md"]
    missing = api.post(f"/v1/quickfire/cards/{uuid.uuid4()}/answer", json={"choice": "a"})
    assert missing.json()["code"] == "card_not_found"


def test_onboarding_seeds_starting_ratings_once(
    api: TestClient, seeded: AsyncSession, auth
) -> None:  # type: ignore[no-untyped-def]
    headers = auth(uuid.uuid4(), login="newcomer")
    assert api.get("/v1/me", headers=headers).json()["prefs"]["onboarded"] is False
    deck = api.get("/v1/onboarding/calibration", headers=headers).json()["cards"]
    tracks = [c["track_slug"] for c in deck]
    assert len(tracks) == len(set(tracks)) == 6  # one per published track

    # Find each card's answer (as a player would after answering), then answer the first right.
    answers = []
    for i, c in enumerate(deck):
        key = api.post(f"/v1/quickfire/cards/{c['id']}/answer", json={"choice": "a"}).json()
        right = key["answer"]
        wrong = next(o["key"] for o in c["options"] if o["key"] != right)
        answers.append({"card_id": c["id"], "choice": right if i == 0 else wrong})
    done = api.post(
        "/v1/me/onboarding",
        json={"experience_level": "2-5", "job_role": "backend", "answers": answers},
        headers=headers,
    )
    assert done.status_code == 200
    body = done.json()
    assert body["me"]["experience_level"] == "2-5"
    assert body["me"]["prefs"]["onboarded"] is True
    assert body["me"]["prefs"]["job_role"] == "backend"
    assert [r["correct"] for r in body["results"]] == [True] + [False] * 5
    assert len(body["seeded_tracks"]) == 6

    # Starting points, not ratings: nothing shows until a rated game.
    assert api.get("/v1/me/ratings", headers=headers).json() == []
    # Again: nothing new is seeded, so calibration can't be farmed.
    again = api.post(
        "/v1/me/onboarding",
        json={"experience_level": "5+", "answers": []},
        headers=headers,
    )
    assert again.json()["seeded_tracks"] == []


def test_onboarding_needs_an_account(api: TestClient, seeded: AsyncSession) -> None:
    assert api.get("/v1/onboarding/calibration").status_code == 401
    assert api.post("/v1/me/onboarding", json={"experience_level": "0-2"}).status_code == 401
