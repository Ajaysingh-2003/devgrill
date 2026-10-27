"""Seeding content/ into Postgres: idempotent, versioned, and strict about bad files."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import ScenarioStatus
from devgrill.infra.models import Scenario, ScenarioVersion, Topic, Track
from devgrill_content.seed import (
    ContentError,
    load_quickfire,
    load_scenarios,
    load_tracks,
    seed,
)

CONTENT = Path(__file__).resolve().parents[3] / "content"


def test_repository_content_is_valid() -> None:
    tracks = load_tracks(CONTENT)
    scenarios = load_scenarios(CONTENT)
    assert len(tracks.tracks) >= 6
    assert len(scenarios) >= 10
    topics = {(t.slug, topic.slug) for t in tracks.tracks for topic in t.topics}
    for path, spec in scenarios:
        assert (spec.track, spec.topic) in topics, path


def test_folder_must_match_slug(tmp_path: Path) -> None:
    shutil.copytree(CONTENT, tmp_path / "content")
    src = tmp_path / "content/scenarios/caching/ttl-zero"
    src.rename(tmp_path / "content/scenarios/caching/renamed")
    with pytest.raises(ContentError, match="must match its folder"):
        load_scenarios(tmp_path / "content")


def test_every_published_track_has_quickfire_cards() -> None:
    tracks = load_tracks(CONTENT)
    cards = load_quickfire(CONTENT, tracks)
    published = {t.slug for t in tracks.tracks if t.status == "published"}
    assert published <= {track for track, _ in cards}


def test_quickfire_slugs_are_unique_and_tracks_known(tmp_path: Path) -> None:
    shutil.copytree(CONTENT, tmp_path / "content")
    root = tmp_path / "content"
    tracks = load_tracks(root)
    caching = yaml.safe_load((root / "quickfire/caching.yaml").read_text(encoding="utf-8"))
    queues = yaml.safe_load((root / "quickfire/queues.yaml").read_text(encoding="utf-8"))
    queues["cards"].append(caching["cards"][0])
    (root / "quickfire/queues.yaml").write_text(yaml.safe_dump(queues), encoding="utf-8")
    with pytest.raises(ContentError, match="is also in"):
        load_quickfire(root, tracks)
    (root / "quickfire/queues.yaml").unlink()
    (root / "quickfire/nope.yaml").write_text(yaml.safe_dump(caching), encoding="utf-8")
    with pytest.raises(ContentError, match="no track 'nope'"):
        load_quickfire(root, tracks)


async def _count(session: AsyncSession, model: type) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


@pytest.mark.integration
async def test_seed_is_idempotent(db_session: AsyncSession) -> None:
    first = await seed(db_session, CONTENT)
    await db_session.commit()
    assert first.versions_new == first.scenarios_new == len(load_scenarios(CONTENT))

    second = await seed(db_session, CONTENT)
    await db_session.commit()
    assert second.versions_new == 0
    assert second.unchanged == first.versions_new
    assert await _count(db_session, ScenarioVersion) == first.versions_new
    assert await _count(db_session, Track) == len(load_tracks(CONTENT).tracks)
    assert await _count(db_session, Topic) == second.topics


@pytest.mark.integration
async def test_changed_scenario_gets_a_new_version(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    root = tmp_path / "content"
    shutil.copytree(CONTENT, root)
    await seed(db_session, root)
    await db_session.commit()

    path = root / "scenarios/caching/ttl-zero/scenario.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc["summary"] = "Updated summary"
    path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    report = await seed(db_session, root)
    await db_session.commit()
    assert report.versions_new == 1

    scenario = (
        await db_session.execute(select(Scenario).where(Scenario.slug == "ttl-zero"))
    ).scalar_one()
    versions = (
        (
            await db_session.execute(
                select(ScenarioVersion)
                .where(ScenarioVersion.scenario_id == scenario.id)
                .order_by(ScenarioVersion.version)
            )
        )
        .scalars()
        .all()
    )
    assert [v.version for v in versions] == [1, 2]
    assert scenario.current_version_id == versions[1].id
    assert scenario.summary == "Updated summary"
    # The published version 1 is untouched (attempts may pin it).
    assert versions[0].spec["summary"] != "Updated summary"
    assert scenario.status is ScenarioStatus.PUBLISHED
