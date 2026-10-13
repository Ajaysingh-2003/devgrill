"""Wire models for /v1 (snake_case JSON; the generated TS client maps to camelCase)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal
from zoneinfo import available_timezones

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

from devgrill.domain.enums import (
    ApproachOutcome,
    AttemptMode,
    AttemptState,
    ChallengeKind,
    Difficulty,
    ExperienceLevel,
    ScenarioStatus,
    StreakMode,
)
from devgrill.domain.spec import BriefingSpec, ServiceKind

ScenarioProgress = Literal["solved", "attempted", "new"]

#: IANA zones (from the pinned tzdata package) as one named enum, so the contract and the
#: generated client share a single `Timezone` type listing exactly the accepted values.
if TYPE_CHECKING:
    Timezone = str  # the members are only known at runtime
else:
    Timezone = StrEnum("Timezone", {zone: zone for zone in sorted(available_timezones())})
DEFAULT_TIMEZONE = Timezone("Asia/Kolkata")


class Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Input(BaseModel):
    """Request bodies: unknown fields are rejected; booleans are StrictBool (no 0 -> False)."""

    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------------- catalog


class TrackProgress(Model):
    solved: int
    attempted: int
    mastery_pct: int = Field(ge=0, le=100)
    rating: float | None


class TrackSummary(Model):
    slug: str
    title: str
    summary: str
    icon: ServiceKind
    position: int
    scenario_count: int
    topics: list[str]
    progress: TrackProgress | None = Field(default=None, description="Only for signed-in callers.")


class ScenarioCard(Model):
    slug: str
    title: str
    summary: str
    difficulty: Difficulty
    est_minutes: int
    tags: list[str]
    track_slug: str
    topic_slug: str | None
    topic_title: str | None
    progress: ScenarioProgress | None = Field(
        default=None, description="Only for signed-in callers."
    )


class TopicOut(Model):
    slug: str
    title: str
    has_primer: bool
    scenarios: list[ScenarioCard]


class TrackDetail(TrackSummary):
    topics_detail: list[TopicOut]


class ScenarioPage(Model):
    items: list[ScenarioCard]
    next_cursor: str | None


class ScenarioStats(Model):
    players: int
    solve_rate_pct: int | None = Field(description="Null until enough attempts have ended.")
    median_minutes: int | None


class Briefing(ScenarioCard):
    version: int
    track_title: str
    briefing: BriefingSpec
    stats: ScenarioStats
    modes: list[AttemptMode]
    warmup: ScenarioCard | None = Field(
        default=None, description="An easier scenario from the same track, if any."
    )


class ApproachOut(Model):
    key: str
    name: str
    outcome: ApproachOutcome
    idea_md: str
    pros: list[str]
    cons: list[str]


class ChallengeOut(Model):
    kind: ChallengeKind
    starts_at: datetime
    ends_at: datetime
    scenario: ScenarioCard
    players: int


# ------------------------------------------------------------------------ profile


class Prefs(Model):
    theme: Literal["system", "light", "dark"] = "system"
    motion: Literal["system", "reduce", "full"] = "system"
    sounds: bool = False
    pro_mode: bool = False
    streak_mode: StreakMode = StreakMode.DAILY
    #: IANA zone used for streak days; India-first default.
    timezone: Timezone = DEFAULT_TIMEZONE


class PrefsPatch(Input):
    theme: Literal["system", "light", "dark"] | None = None
    motion: Literal["system", "reduce", "full"] | None = None
    sounds: StrictBool | None = None
    pro_mode: StrictBool | None = None
    streak_mode: StreakMode | None = None
    timezone: Timezone | None = None


class Me(Model):
    user_id: uuid.UUID
    handle: str
    display_name: str
    avatar_url: str | None
    country: str | None
    experience_level: ExperienceLevel | None
    roles: list[str]
    prefs: Prefs
    is_public: bool
    created_at: datetime


class MePatch(Input):
    """Omit a field to keep it. `country` and `experience_level` accept null to clear them;
    the others can't be null (the schema shows them as non-nullable)."""

    # Constraints sit on the str member: on the union they would also run against None.
    display_name: Annotated[str, Field(min_length=1, max_length=60)] | SkipJsonSchema[None] = None
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    experience_level: ExperienceLevel | None = None
    is_public: StrictBool | SkipJsonSchema[None] = None
    prefs: PrefsPatch | SkipJsonSchema[None] = None

    @model_validator(mode="after")
    def _no_explicit_nulls(self) -> MePatch:
        for name in ("display_name", "is_public", "prefs"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} can't be null")
        return self


class RatingPoint(Model):
    ts: datetime
    rating: float


class TrackRating(Model):
    track_slug: str
    track_title: str
    rating: float
    rd: float
    games: int
    history: list[RatingPoint]


class TopicProgress(Model):
    slug: str
    title: str
    solved: int
    total: int


class TrackProgressDetail(Model):
    track_slug: str
    track_title: str
    solved: int
    attempted: int
    total: int
    mastery_pct: int
    topics: list[TopicProgress]


class StreakOut(Model):
    mode: StreakMode
    current: int
    longest: int
    freezes: int
    last_day: date | None
    #: Active days in the heatmap window (oldest first), for the profile's activity grid.
    days: list[date]
    window_start: date


class AttemptSummary(Model):
    id: uuid.UUID
    track_slug: str
    scenario_slug: str
    scenario_title: str
    difficulty: Difficulty
    mode: AttemptMode
    state: AttemptState
    started_at: datetime
    ended_at: datetime | None


class AttemptPage(Model):
    items: list[AttemptSummary]
    next_cursor: str | None


class ClaimGuestIn(Input):
    guest_token: str = Field(min_length=20, max_length=2000)


class ClaimGuestOut(Model):
    claimed: int


class GuestTokenOut(Model):
    token: str
    expires_at: datetime


class PublicProfile(Model):
    handle: str
    display_name: str
    avatar_url: str | None
    created_at: datetime
    resolved: int
    ratings: list[TrackRating]


# -------------------------------------------------------------------------- admin


class AdminScenario(Model):
    slug: str
    title: str
    track_slug: str
    difficulty: Difficulty
    status: ScenarioStatus
    version: int | None
    attempts: int
    resolved: int
    updated_at: datetime


class AdminScenarioPage(Model):
    items: list[AdminScenario]
    next_cursor: str | None


# ------------------------------------------------------------------------ internal


class ProfileHookIn(Input):
    """Sent by the web app's Better Auth hook after a user is created or signs in."""

    user_id: uuid.UUID
    login: str | None = Field(default=None, max_length=39)
    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    image: HttpUrl | None = None


class ProfileHookOut(Model):
    user_id: uuid.UUID
    handle: str
    created: bool
