"""Wire models for /v1 (snake_case JSON; the generated TS client maps to camelCase)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import StrEnum
from importlib.resources import files
from typing import TYPE_CHECKING, Annotated, Literal

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
    # From the pinned tzdata package, not available_timezones(): on Linux that also lists the
    # system zoneinfo (e.g. "localtime"), so the contract would differ between machines.
    _ZONES = files("tzdata").joinpath("zones").read_text(encoding="utf-8").split()
    Timezone = StrEnum("Timezone", {zone: zone for zone in sorted(_ZONES)})
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


class AttemptIn(Input):
    scenario_slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=64)
    mode: AttemptMode = AttemptMode.GUIDED


class AttemptOut(Model):
    id: uuid.UUID
    scenario_slug: str
    mode: AttemptMode
    state: AttemptState
    started_at: datetime
    active_at: datetime | None
    ended_at: datetime | None
    #: When the sandbox is torn down unless extended (set once it is up).
    expires_at: datetime | None


ToolId = Literal["overview", "logs", "terminal", "database", "cache", "code", "deploys", "war_room"]


class PageOut(Model):
    severity: Literal["SEV1", "SEV2", "SEV3", "SEV4"]
    title: str


class SloTarget(Model):
    lt: float | None = None
    gt: float | None = None


class HintOut(Model):
    tier: int
    text: str


class WorkspaceOut(Model):
    """Everything the incident workspace needs to render before the live streams connect."""

    attempt: AttemptOut
    scenario_title: str
    track_slug: str
    difficulty: Difficulty
    page: PageOut | None
    unlocked_tools: list[ToolId]
    #: Metrics the telemetry stream carries, and the SLO the charts draw.
    metrics: list[str]
    slo: dict[str, SloTarget]
    #: Services whose source the player can edit and deploy.
    deployable: list[str]
    hints_total: int
    hints: list[HintOut]
    extend_minutes: int
    extends_left: int
    #: Minutes without player activity before the sandbox is torn down (warn before it).
    idle_minutes: int
    gateway_url: str


class TicketIn(Input):
    kind: Literal["terminal", "telemetry"]


class TicketOut(Model):
    ticket: str
    url: str
    expires_in: int


class MessageIn(Input):
    text: str = Field(min_length=1, max_length=1000)


class MitigationOut(Model):
    """A "declare mitigated" claim, scored against the real state the workflow detected."""

    declared: bool
    real_state: AttemptState
    correct: bool


class ServiceStatus(Model):
    name: str
    state: str | None
    health: str | None
    restarts: int
    oom_killed: bool
    started_at: str | None


class StatusOut(Model):
    services: list[ServiceStatus]


class FilesOut(Model):
    service: str
    files: list[str]


class FileOut(Model):
    service: str
    path: str
    content: str


class FileIn(Input):
    content: str = Field(max_length=256 * 1024)


class FileSaved(Model):
    service: str
    path: str
    saved: bool


class Commit(Model):
    sha: str
    short: str
    author: str
    at: int
    message: str


class DeployHistoryOut(Model):
    service: str
    commits: list[Commit]
    live: str | None
    live_dirty: bool


class DeployIn(Input):
    service: str | None = Field(default=None, max_length=40)


class RollbackIn(Input):
    service: str | None = Field(default=None, max_length=40)
    ref: str = Field(pattern=r"^[0-9a-f]{4,40}$")


class RestartIn(Input):
    service: str = Field(max_length=40)


class DeployOut(Model):
    ok: bool
    sha: str
    message: str
    log: str


class RestartOut(Model):
    message: str


class DbStatement(Model):
    query: str
    calls: int
    mean_ms: float
    total_ms: float
    rows: int


class DbConnections(Model):
    state: str
    n: int


class DbSession(Model):
    pid: int
    user: str | None
    state: str | None
    wait_event_type: str | None
    wait_event: str | None
    seconds: float | None
    query: str | None
    blocked_by: list[int]


class DbInsightsOut(Model):
    max_connections: int
    connections: list[DbConnections]
    top: list[DbStatement]
    active: list[DbSession]


class QueryIn(Input):
    sql: str = Field(min_length=1, max_length=4000)


Cell = str | int | float | bool | None


class QueryOut(Model):
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Cell]] = Field(default_factory=list)
    truncated: bool = False
    ms: float | None = None
    error: str | None = None


class CacheStats(Model):
    hits: int
    misses: int
    hit_rate: float | None
    ops_per_sec: int
    used_memory: int
    maxmemory: int
    evicted_keys: int
    keys: int
    clients: int


class CacheKey(Model):
    key: str
    ttl: int


class AskedKey(Model):
    key: str
    count: int
    exists: bool


class CacheOut(Model):
    stats: CacheStats
    keys: list[CacheKey]
    asked: list[AskedKey]
    window_s: float


class Quota(Model):
    used: float
    limit: int
    period: Literal["day", "week", "ever"]
    resets_at: datetime | None


class UsageOut(Model):
    """What the caller may still start (ADR 013). Guests are reported per guest token."""

    tier: Literal["guest", "free", "pro", "team"]
    live_starts: Quota
    sandbox_minutes: Quota
    session_minutes: int
    idle_minutes: int
    #: Free sandboxes are paused (daily budget spent, or switched off); cards and case files
    #: stay open.
    free_paused: bool


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
