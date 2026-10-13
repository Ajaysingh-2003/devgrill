"""Content file shapes (`content/tracks.yaml`, `content/scenarios/<track>/<slug>/scenario.yaml`).

Validated once when content is loaded and again when the API reads a stored spec, so a bad
file fails the seed or CI instead of breaking a page. Phase 3 extends ScenarioSpec with
faults, probes, hints and the rubric.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from devgrill.domain.enums import Difficulty, ScenarioStatus, TrackStatus

Slug = str  # validated by the patterns below
SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
ServiceKind = Literal["api", "worker", "db", "cache", "queue", "lb"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SystemNode(_Strict):
    kind: ServiceKind
    name: str = Field(max_length=40)
    note: str = Field(max_length=80)
    #: "path" nodes are on the request path (drawn left to right); "side" ones run beside it.
    role: Literal["path", "side"] = "path"


class Goal(_Strict):
    title: str = Field(max_length=60)
    detail: str = Field(max_length=200)


class BriefingSpec(_Strict):
    story: str = Field(max_length=600)
    system: list[SystemNode] = Field(default_factory=list, max_length=12)
    goals: list[Goal] = Field(default_factory=list, max_length=6)


class ScenarioSpec(_Strict):
    slug: Slug = Field(pattern=SLUG_PATTERN, max_length=64)
    title: str = Field(max_length=80)
    track: Slug = Field(pattern=SLUG_PATTERN)
    topic: Slug | None = Field(default=None, pattern=SLUG_PATTERN)
    difficulty: Difficulty
    est_minutes: int = Field(ge=1, le=240)
    status: ScenarioStatus = ScenarioStatus.DRAFT
    summary: str = Field(max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=12)
    base_app: Slug = Field(pattern=SLUG_PATTERN)
    briefing: BriefingSpec


class TopicSpec(_Strict):
    slug: Slug = Field(pattern=SLUG_PATTERN, max_length=64)
    title: str = Field(max_length=60)
    primer: str | None = Field(default=None, max_length=4000)


class TrackSpec(_Strict):
    slug: Slug = Field(pattern=SLUG_PATTERN, max_length=64)
    title: str = Field(max_length=60)
    icon: ServiceKind
    summary: str = Field(max_length=200)
    status: TrackStatus = TrackStatus.PUBLISHED
    topics: list[TopicSpec] = Field(default_factory=list)


class TracksFile(_Strict):
    tracks: list[TrackSpec]
