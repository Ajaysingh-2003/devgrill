"""Load content/ into the database (`just db-seed`). Safe to run any number of times.

- Tracks and topics are upserted by slug.
- Each scenario file is hashed. An unchanged file does nothing; a changed one becomes a new
  scenario version (published versions are immutable; attempts pin the version they played),
  and the scenario's `current_version_id` moves to it.
- A version's probes, hints and rubric are stored with it (verify results point at the
  probes; versions seeded before phase 5 get theirs filled in).
- Known approaches (`approaches/*.yaml`, never the cheats) are upserted by key for the debrief.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from devgrill.domain.enums import ApproachOutcome, ScenarioStatus
from devgrill.domain.spec import ApproachSpec, ScenarioSpec, TracksFile
from devgrill.infra.models import (
    Approach,
    BaseApp,
    Hint,
    Probe,
    Rubric,
    Scenario,
    ScenarioVersion,
    Topic,
    Track,
)


class ContentError(Exception):
    """A content file is missing, malformed or refers to something that doesn't exist."""


@dataclass
class SeedReport:
    tracks: int = 0
    topics: int = 0
    scenarios_new: int = 0
    versions_new: int = 0
    unchanged: int = 0
    approaches: int = 0
    problems: list[str] = field(default_factory=list)


def load_tracks(root: Path) -> TracksFile:
    path = root / "tracks.yaml"
    try:
        return TracksFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ContentError(f"{path}: {exc}") from exc


def load_scenarios(root: Path) -> list[tuple[Path, ScenarioSpec]]:
    specs: list[tuple[Path, ScenarioSpec]] = []
    for path in sorted((root / "scenarios").glob("*/*/scenario.yaml")):
        try:
            spec = ScenarioSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except (yaml.YAMLError, ValidationError) as exc:
            raise ContentError(f"{path}: {exc}") from exc
        track_dir, slug_dir = path.parent.parent.name, path.parent.name
        if (spec.track, spec.slug) != (track_dir, slug_dir):
            raise ContentError(f"{path}: track/slug must match its folder ({track_dir}/{slug_dir})")
        specs.append((path, spec))
    return specs


def content_hash(spec: ScenarioSpec) -> str:
    canonical = json.dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


async def seed(session: AsyncSession, root: Path, *, now: datetime | None = None) -> SeedReport:
    tracks_file = load_tracks(root)
    scenarios = load_scenarios(root)
    stamp = now or datetime.now(UTC)
    report = SeedReport()

    track_ids: dict[str, uuid.UUID] = {}
    topic_ids: dict[tuple[str, str], uuid.UUID] = {}
    for position, t in enumerate(tracks_file.tracks):
        values = {
            "slug": t.slug,
            "title": t.title,
            "summary": t.summary,
            "icon": t.icon,
            "position": position,
            "status": t.status,
        }
        stmt = insert(Track).values(**values)
        track_id = (
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["slug"],
                    set_={k: stmt.excluded[k] for k in values if k != "slug"},
                ).returning(Track.id)
            )
        ).scalar_one()
        track_ids[t.slug] = track_id
        report.tracks += 1
        for topic_position, topic in enumerate(t.topics):
            topic_values = {
                "track_id": track_id,
                "slug": topic.slug,
                "title": topic.title,
                "primer_md": topic.primer,
                "position": topic_position,
            }
            topic_stmt = insert(Topic).values(**topic_values)
            topic_ids[(t.slug, topic.slug)] = (
                await session.execute(
                    topic_stmt.on_conflict_do_update(
                        constraint="uq_topics_track_id_slug",
                        set_={
                            k: topic_stmt.excluded[k] for k in ("title", "primer_md", "position")
                        },
                    ).returning(Topic.id)
                )
            ).scalar_one()
            report.topics += 1

    base_apps: dict[str, uuid.UUID] = {}
    for _, spec in scenarios:
        if spec.base_app not in base_apps:
            stmt = insert(BaseApp).values(slug=spec.base_app, name=spec.base_app, version="0")
            base_apps[spec.base_app] = (
                await session.execute(
                    stmt.on_conflict_do_update(
                        index_elements=["slug"], set_={"slug": stmt.excluded.slug}
                    ).returning(BaseApp.id)
                )
            ).scalar_one()

    for path, spec in scenarios:
        if spec.track not in track_ids:
            raise ContentError(f"{path}: unknown track {spec.track!r}")
        topic_id = None
        if spec.topic is not None:
            topic_id = topic_ids.get((spec.track, spec.topic))
            if topic_id is None:
                raise ContentError(f"{path}: unknown topic {spec.topic!r} in {spec.track!r}")

        values = {
            "slug": spec.slug,
            "track_id": track_ids[spec.track],
            "topic_id": topic_id,
            "title": spec.title,
            "summary": spec.summary,
            "difficulty": spec.difficulty,
            "est_minutes": spec.est_minutes,
            "status": spec.status,
            "access": spec.access,
            "tags": spec.tags,
        }
        stmt = insert(Scenario).values(**values)
        scenario_id, inserted = (
            await session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["slug"],
                    set_={k: stmt.excluded[k] for k in values if k != "slug"},
                ).returning(Scenario.id, (Scenario.current_version_id.is_(None)).label("fresh"))
            )
        ).one()
        if inserted:
            report.scenarios_new += 1

        digest = content_hash(spec)
        current = (
            await session.execute(
                select(ScenarioVersion)
                .join(Scenario, Scenario.current_version_id == ScenarioVersion.id)
                .where(Scenario.id == scenario_id)
            )
        ).scalar_one_or_none()
        report.approaches += await _approaches(session, scenario_id, path.parent)
        if current is not None and current.content_hash == digest:
            report.unchanged += 1
            if not await session.scalar(
                select(func.count())
                .select_from(Probe)
                .where(Probe.scenario_version_id == current.id)
            ):
                await _version_rows(session, current.id, spec)
            continue

        next_version = (
            await session.execute(
                select(func.coalesce(func.max(ScenarioVersion.version), 0) + 1).where(
                    ScenarioVersion.scenario_id == scenario_id
                )
            )
        ).scalar_one()
        version = ScenarioVersion(
            scenario_id=scenario_id,
            version=next_version,
            spec=spec.model_dump(mode="json"),
            content_hash=digest,
            base_app_id=base_apps[spec.base_app],
            published_at=stamp if spec.status is ScenarioStatus.PUBLISHED else None,
        )
        session.add(version)
        await session.flush()
        await _version_rows(session, version.id, spec)
        scenario = await session.get(Scenario, scenario_id)
        assert scenario is not None
        scenario.current_version_id = version.id
        report.versions_new += 1

    await session.flush()
    return report


async def _version_rows(session: AsyncSession, version_id: uuid.UUID, spec: ScenarioSpec) -> None:
    """The probes, hints and rubric a version pins."""
    for probe in spec.probes:
        session.add(
            Probe(
                scenario_version_id=version_id,
                key=probe.key,
                kind=probe.kind,
                config=probe.model_dump(
                    mode="json", include={"title", "how", "script", "steps", "multiplier"}
                ),
                target={k: v.model_dump(mode="json") for k, v in probe.target.items()},
                weight=probe.weight,
            )
        )
    if spec.hints is not None:
        for tier, body in enumerate((spec.hints.tier1, spec.hints.tier2, spec.hints.tier3), 1):
            session.add(Hint(scenario_version_id=version_id, tier=tier, body_md=body))
    if spec.rubric:
        session.add(
            Rubric(
                scenario_version_id=version_id,
                criteria=[c.model_dump(mode="json") for c in spec.rubric],
            )
        )
    await session.flush()


async def _approaches(session: AsyncSession, scenario_id: uuid.UUID, folder: Path) -> int:
    """Upsert the scenario's known approaches (cheats stay in the content tests)."""
    count = 0
    for path in sorted((folder / "approaches").glob("*.yaml")):
        try:
            spec = ApproachSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except (ValidationError, yaml.YAMLError) as exc:
            raise ContentError(f"{path}: {exc}") from exc
        if spec.cheat:
            continue
        patches = [
            (path.parent / s.patch).read_text(encoding="utf-8") for s in spec.steps if s.patch
        ]
        values = {
            "scenario_id": scenario_id,
            "key": spec.key,
            "name": spec.name,
            "outcome": ApproachOutcome(spec.outcome),
            "idea_md": spec.idea,
            "exemplar_patch": "\n".join(patches) or None,
            "pros": spec.pros,
            "cons": spec.cons,
        }
        stmt = insert(Approach).values(**values)
        await session.execute(
            stmt.on_conflict_do_update(
                constraint="uq_approaches_scenario_id_key",
                set_={k: stmt.excluded[k] for k in values if k not in ("scenario_id", "key")},
            )
        )
        count += 1
    return count
