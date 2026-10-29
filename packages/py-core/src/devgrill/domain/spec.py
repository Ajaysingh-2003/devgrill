"""Content file shapes: `content/tracks.yaml`, `scenario.yaml`, `fault.yaml`, `approach.yaml`.

Spec v1 (ADR 012). Validated when content is loaded (seed, `devgrill-content validate`) and
again when the API reads a stored spec, so a bad file fails CI instead of a page or a sandbox.
`devgrill-content schema` exports these as JSON Schema for editor autocompletion.

Scenarios are runtime-agnostic: nothing here names Docker. Fault modules describe *what* to
change in a base app (a patch, a config override, a Toxiproxy toxic, a data script); the
driver decides *how*.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from devgrill.domain.enums import (
    Access,
    AttemptMode,
    Difficulty,
    FaultKind,
    ProbeKind,
    QuickfireKind,
    ScenarioStatus,
    TrackStatus,
)

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
Slug = Annotated[str, Field(pattern=SLUG_PATTERN, max_length=64)]
#: Fault reference: `<category>/<name>`, e.g. `cache/key-format-change`.
FaultRef = Annotated[str, Field(pattern=r"^[a-z0-9-]+/[a-z0-9-]+$", max_length=80)]
#: A compose service name inside the base app.
ServiceName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,30}$")]


def _relative_path(value: str) -> str:
    """A path inside the scenario (or fault) folder: never absolute, never climbing out."""
    if not re.fullmatch(r"[A-Za-z0-9_./-]{1,200}", value) or value.startswith("/"):
        raise ValueError(f"{value!r} is not a relative path")
    if any(part == ".." for part in value.split("/")):
        raise ValueError(f"{value!r} must not leave the content folder")
    return value


RelPath = Annotated[str, AfterValidator(_relative_path)]
ServiceKind = Literal["api", "worker", "db", "cache", "queue", "lb"]

_OFFSET = re.compile(r"^T([+-])(\d+)(s|m)$")


def parse_offset(value: str) -> int:
    """`T-2m` -> -120, `T+30s` -> 30. T is the moment load (the "sale") starts."""
    match = _OFFSET.match(value)
    if not match:
        raise ValueError(f"bad time offset {value!r}; use T-2m, T+30s, ...")
    sign, amount, unit = match.groups()
    seconds = int(amount) * (60 if unit == "m" else 1)
    return -seconds if sign == "-" else seconds


class _Strict(BaseModel):
    # By alias in YAML ("schema"), by name when read back from a stored model_dump().
    model_config = ConfigDict(
        extra="forbid", frozen=True, validate_by_name=True, validate_by_alias=True
    )


# ------------------------------------------------------------------------------- briefing


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


# ------------------------------------------------------------------------- faults (modules)


class SymptomContract(_Strict):
    """What a fault must do to the system, asserted by `devgrill-content test`."""

    metric: str = Field(max_length=60, description="A verifier metric, e.g. error_rate.")
    op: Literal["gt", "lt"]
    value: float
    within_s: int = Field(ge=5, le=600, default=60)


class FaultParam(_Strict):
    type: Literal["string", "integer", "number", "boolean"]
    description: str = Field(max_length=200)
    default: str | int | float | bool | None = None


class FaultApply(_Strict):
    """How a fault changes the base app. Exactly one mechanism per fault."""

    #: Unified diff applied to the service's source (code_patch) or a config file (config).
    patch: RelPath | None = None
    #: Environment overrides for a service: {"CACHE_TTL_SECONDS": "{{ttl}}"}; restarts it.
    env: dict[str, str] | None = None
    #: Toxiproxy toxics on a proxy: {"proxy": "postgres", "type": "latency", ...}.
    toxic: dict[str, str | int | float] | None = None
    #: A script run once inside a service: .sql with psql, .py with python3, .sh with sh.
    script: RelPath | None = None
    #: Leave the script running (e.g. a transaction that holds a lock and never commits).
    detach: bool = False
    #: Service to apply to (patch, env, script).
    service: ServiceName | None = None

    @model_validator(mode="after")
    def _one_mechanism(self) -> FaultApply:
        mechanisms = [m for m in (self.patch, self.env, self.toxic, self.script) if m]
        if len(mechanisms) != 1:
            raise ValueError("a fault applies exactly one of: patch, env, toxic, script")
        if (self.patch or self.env or self.script) and not self.service:
            raise ValueError("patch, env and script faults need a service")
        if self.detach and not self.script:
            raise ValueError("only scripts can be detached")
        if self.script and not self.script.endswith((".sql", ".py", ".sh")):
            raise ValueError("fault scripts are .sql, .py or .sh")
        return self


class FaultSpec(_Strict):
    """`content/faults/<category>/<name>/fault.yaml`."""

    schema_: Literal["devgrill/fault@1"] = Field(alias="schema")
    name: FaultRef
    kind: FaultKind
    summary: str = Field(max_length=200)
    #: Base apps this fault is written for (its patch paths and service names).
    base_apps: list[Slug] = Field(min_length=1)
    params: dict[str, FaultParam] = Field(default_factory=dict)
    apply: FaultApply
    #: An optional second step (e.g. config change plus the data that triggers it).
    also: FaultApply | None = None
    #: Reverting a patch/env/toxic is automatic; data faults say how to undo.
    revert: FaultApply | None = None
    symptom: SymptomContract
    #: Shown in the deploy history (deploy-shaped faults) or hidden (infra faults).
    deploy_message: str | None = Field(default=None, max_length=80)


# ------------------------------------------------------------------- scenario sub-sections


class FaultStep(_Strict):
    use: FaultRef
    #: When it happens relative to T (load start). Negative means "before the page".
    at: str = Field(pattern=_OFFSET.pattern)
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @property
    def at_seconds(self) -> int:
        return parse_offset(self.at)


class LoadProfile(_Strict):
    """The traffic the verifier replays against the sandbox; also the "sale" during play."""

    script: RelPath = Field(description="k6 script relative to the base app's load/ folder.")
    vus: int = Field(ge=1, le=200, default=20)
    duration: str = Field(pattern=r"^\d+[sm]$", default="3m")
    params: dict[str, str | int | float] = Field(default_factory=dict)


class Page(_Strict):
    severity: Literal["SEV1", "SEV2", "SEV3", "SEV4"]
    title: str = Field(max_length=120)


class DeployEntry(_Strict):
    """A commit in the sandbox's git history. Its real sha is made when the sandbox boots."""

    message: str = Field(max_length=80)
    #: Minutes before T this deploy happened (for `git log` and the Deploys panel).
    minutes_before: int = Field(ge=0, le=100_000)
    #: The service whose repo has this commit; unset, every patchable service's repo has it.
    service: ServiceName | None = None
    #: If set, this deploy *is* the fault's change (the patch is committed under this sha).
    from_fault: FaultRef | None = None


class Beat(_Strict):
    """A scripted teammate message, by time or by event (never generated by the LLM)."""

    persona: Slug
    say: str = Field(max_length=400)
    #: When, after T. Timed beats only fire while the incident is still active: once it is
    #: mitigated (or ended) they stay quiet, so nobody asks about a problem that's gone.
    at: str | None = Field(default=None, pattern=_OFFSET.pattern)
    #: An event name, e.g. "state:mitigated". (Not `on`: YAML 1.1 reads that key as true.)
    when: str | None = Field(default=None, pattern=r"^[a-z0-9_.\-]+(:[a-z0-9_]+)?$", max_length=60)

    @property
    def at_seconds(self) -> int:
        return parse_offset(self.at) if self.at else 0

    @model_validator(mode="after")
    def _one_trigger(self) -> Beat:
        if bool(self.at) == bool(self.when):
            raise ValueError("a beat has exactly one of: at, when")
        return self


class Constraints(_Strict):
    """Budget probe: fixes that just buy bigger hardware fail."""

    no_scale_up: list[ServiceName] = Field(default_factory=list)
    cache_max_memory_mb: int | None = Field(default=None, ge=16)


class ProbeTarget(_Strict):
    """Thresholds per metric: {"p99_ms": {"lt": 500}}."""

    lt: float | None = None
    gt: float | None = None

    @model_validator(mode="after")
    def _some_bound(self) -> ProbeTarget:
        if self.lt is None and self.gt is None:
            raise ValueError("a target needs lt or gt")
        return self

    def holds(self, value: float) -> bool:
        return (self.lt is None or value < self.lt) and (self.gt is None or value > self.gt)


class Slo(_Strict):
    """The health condition for "mitigated": every threshold holds for `for_s` seconds.

    Latency and errors are the usual page; `thresholds` adds base-app metrics for incidents
    that are about capacity or correctness rather than users waiting (e.g. database load).
    """

    p99_latency_ms: float | None = Field(default=None, gt=0)
    error_rate: float | None = Field(default=None, ge=0, le=1)
    thresholds: dict[str, ProbeTarget] = Field(default_factory=dict)
    for_s: int = Field(ge=10, le=600, default=60)

    @model_validator(mode="after")
    def _some_threshold(self) -> Slo:
        if self.p99_latency_ms is None and self.error_rate is None and not self.thresholds:
            raise ValueError("an SLO needs at least one threshold")
        return self

    def targets(self) -> dict[str, ProbeTarget]:
        """Every threshold as {base-app metric: target}."""
        out = dict(self.thresholds)
        if self.p99_latency_ms is not None:
            out["p99_latency_ms"] = ProbeTarget(lt=self.p99_latency_ms)
        if self.error_rate is not None:
            out["error_rate"] = ProbeTarget(lt=self.error_rate)
        return out


class ChaosStep(_Strict):
    """One chaos action the verifier performs (outside the sandbox) before measuring."""

    del_key: str | None = Field(default=None, max_length=120)
    flush_cache: bool | None = None
    restart: ServiceName | None = None
    toxic: dict[str, str | int | float] | None = None
    #: SQL run as the app's database user and held for the whole chaos window (e.g. a stalled
    #: migration holding a lock); its session is ended when the window closes.
    hold_sql: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _one_action(self) -> ChaosStep:
        actions = [
            a
            for a in (self.del_key, self.flush_cache, self.restart, self.toxic, self.hold_sql)
            if a
        ]
        if len(actions) != 1:
            raise ValueError("a chaos step does exactly one thing")
        return self


class ProbeSpec(_Strict):
    key: Slug
    kind: ProbeKind
    title: str = Field(max_length=60)
    how: str = Field(max_length=120, description="One line shown on the debrief.")
    weight: float = Field(gt=0, le=10, default=1.0)
    #: load: k6 script (relative to verify/); invariant: a python/SQL check; hidden_test: a folder.
    script: RelPath | None = None
    steps: list[ChaosStep] = Field(default_factory=list, max_length=8)
    target: dict[str, ProbeTarget] = Field(default_factory=dict)
    #: Load probes replay this many times the base profile.
    multiplier: float = Field(gt=0, le=50, default=1.0)

    @model_validator(mode="after")
    def _shape_per_kind(self) -> ProbeSpec:
        match self.kind:
            case ProbeKind.LOAD:
                if not self.target:
                    raise ValueError("a load probe needs a target")
            case ProbeKind.CHAOS:
                if not self.steps or not self.target:
                    raise ValueError("a chaos probe needs steps and a target")
            case ProbeKind.INVARIANT | ProbeKind.HIDDEN_TEST:
                if not self.script:
                    raise ValueError(f"a {self.kind.value} probe needs a script")
            case ProbeKind.BUDGET:
                pass
        return self


class ScoringWeights(_Strict):
    mitigation_time: float = Field(ge=0, le=1, default=0.25)
    resolution: float = Field(ge=0, le=1, default=0.4)
    postmortem: float = Field(ge=0, le=1, default=0.25)
    communication: float = Field(ge=0, le=1, default=0.1)

    @model_validator(mode="after")
    def _sums_to_one(self) -> ScoringWeights:
        total = self.mitigation_time + self.resolution + self.postmortem + self.communication
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scoring weights must sum to 1 (got {total})")
        return self


class RubricCriterion(_Strict):
    key: Slug
    max: int = Field(ge=1, le=10)
    description: str = Field(max_length=200)
    #: Example answers for each score band, so grading is consistent.
    anchors: dict[str, str] = Field(default_factory=dict)


class ReplayRule(_Strict):
    """A marker on the debrief's investigation replay, for an event the player caused.

    `when` is a trigger (see devgrill.domain.events): `postgres-db.restarted`, `db.query`,
    `api.rolledback`, `state:mitigated`... `match` narrows it with a regular expression over
    the event's text (a console query, a deploy's diff summary).
    """

    when: str = Field(pattern=r"^[a-z0-9_.\-]+(:[a-z0-9_]+)?$", max_length=60)
    match: str | None = Field(default=None, max_length=200)
    mark: Literal["clue", "lost"]
    note: str = Field(max_length=200)

    @field_validator("match")
    @classmethod
    def _compiles(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"match is not a valid regular expression: {exc}") from exc
        return value


class Hints(_Strict):
    """Three tiers: a nudge, a direction, a near-answer."""

    tier1: str = Field(max_length=400)
    tier2: str = Field(max_length=400)
    tier3: str = Field(max_length=600)


class AiSpec(_Strict):
    """How the AI teammates treat this scenario (ADR 016)."""

    #: Regular expressions (case-insensitive) for the root cause and the fix. Teammates may not
    #: say them before the player has taken hint `reveal_at`; replies that do are withheld.
    spoilers: list[str] = Field(default_factory=list, max_length=20)
    reveal_at: int = Field(default=3, ge=1, le=3)
    #: Who is in the war room (persona slugs). Defaults to the personas the beats use.
    personas: list[Slug] = Field(default_factory=list, max_length=4)
    #: One plain sentence of what really happened, for graders and coach notes (never shown
    #: to teammates). Defaults to the solution's summary.
    root_cause: str | None = Field(default=None, max_length=600)

    @field_validator("spoilers")
    @classmethod
    def _compile(cls, values: list[str]) -> list[str]:
        for value in values:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(f"spoiler {value!r} is not a valid pattern: {exc}") from exc
        return values


# -------------------------------------------------------------------------------- scenario


class ScenarioSpec(_Strict):
    """`content/scenarios/<track>/<slug>/scenario.yaml`.

    A playable scenario (`status: published`) must have faults, a load profile, an SLO and
    probes. Drafts may omit them while they are being written.
    """

    schema_: Literal["devgrill/scenario@1"] = Field(alias="schema", default="devgrill/scenario@1")
    slug: Slug
    title: str = Field(max_length=80)
    track: Slug
    topic: Slug | None = None
    difficulty: Difficulty
    est_minutes: int = Field(ge=1, le=240)
    status: ScenarioStatus = ScenarioStatus.DRAFT
    summary: str = Field(max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=12)
    base_app: Slug
    briefing: BriefingSpec
    #: Not yet runnable as a sandbox (metadata only, e.g. a placeholder in the library).
    playable: bool = True
    #: In the Daily and Weekly rotation (playable scenarios only). Authors opt a scenario
    #: out when it needs context a cold player won't have.
    daily: bool = True
    #: Which plans may play it live (ADR 013). The Daily Incident is open to every plan.
    access: Access = Access.PRO

    page: Page | None = None
    faults: list[FaultStep] = Field(default_factory=list, max_length=6)
    load: LoadProfile | None = None
    deploy_history: list[DeployEntry] = Field(default_factory=list, max_length=12)
    beats: list[Beat] = Field(default_factory=list, max_length=20)
    unlocked_tools: list[
        Literal["overview", "logs", "terminal", "database", "cache", "code", "deploys", "war_room"]
    ] = Field(
        default_factory=lambda: [
            "overview",
            "logs",
            "terminal",
            "database",
            "cache",
            "code",
            "deploys",
            "war_room",
        ]
    )
    modes: list[AttemptMode] = Field(
        default_factory=lambda: [AttemptMode.GUIDED, AttemptMode.ONCALL]
    )
    #: The Overview's charts, in order (base-app metric names); empty shows the base app's own
    #: order. Pick the signals this incident is read from.
    charts: list[str] = Field(default_factory=list, max_length=6)
    slo: Slo | None = None
    constraints: Constraints = Field(default_factory=Constraints)
    probes: list[ProbeSpec] = Field(default_factory=list, max_length=12)
    scoring: ScoringWeights = Field(default_factory=ScoringWeights)
    hints: Hints | None = None
    rubric: list[RubricCriterion] = Field(default_factory=list, max_length=8)
    #: Minutes a sandbox lives (hard TTL). Defaults to the platform setting.
    ttl_minutes: int | None = Field(default=None, ge=10, le=120)
    #: Par for mitigation, in minutes after the page: full mitigation-time credit up to here.
    #: Defaults to half of `est_minutes`.
    par_minutes: int | None = Field(default=None, ge=1, le=120)
    #: Markers on the debrief's investigation replay (key clues, lost time).
    replay: list[ReplayRule] = Field(default_factory=list, max_length=20)
    ai: AiSpec = Field(default_factory=AiSpec)

    @property
    def mitigation_par_minutes(self) -> int:
        return self.par_minutes or max(1, self.est_minutes // 2)

    @field_validator("probes")
    @classmethod
    def _unique_probe_keys(cls, probes: list[ProbeSpec]) -> list[ProbeSpec]:
        keys = [p.key for p in probes]
        if len(keys) != len(set(keys)):
            raise ValueError("probe keys must be unique")
        return probes

    @model_validator(mode="after")
    def _playable_is_complete(self) -> ScenarioSpec:
        if self.status is ScenarioStatus.PUBLISHED and self.playable:
            missing = [
                name
                for name, value in (
                    ("page", self.page),
                    ("faults", self.faults),
                    ("load", self.load),
                    ("slo", self.slo),
                    ("probes", self.probes),
                    ("hints", self.hints),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"a published playable scenario needs: {', '.join(missing)}")
            if not any(p.kind is ProbeKind.HIDDEN_TEST for p in self.probes):
                raise ValueError(
                    "a published playable scenario needs a hidden_test probe (the anti-cheat"
                    " correctness check, e.g. script: base/correctness.py)"
                )
        for entry in self.deploy_history:
            if entry.from_fault and entry.from_fault not in {f.use for f in self.faults}:
                raise ValueError(
                    f"deploy {entry.message!r} refers to a fault the scenario doesn't use"
                )
        # Fault deploys are committed when the fault is applied, after the plain history, so
        # they must also be the most recent entries for `git log` to read in time order.
        plain = [e.minutes_before for e in self.deploy_history if not e.from_fault]
        faulty = [e.minutes_before for e in self.deploy_history if e.from_fault]
        if plain and faulty and min(plain) <= max(faulty):
            raise ValueError("deploys made by faults must be newer than the rest of the history")
        return self


# -------------------------------------------------------------------------------- solution


class SolutionStep(_Strict):
    """One step of a fix: a patch to a service's repo (committed and deployed), a command, or
    a rollback to an earlier deploy (by its message in the deploy history)."""

    patch: RelPath | None = None
    #: A shell command run in `service` (e.g. `redis-cli -h redis-db LREM ...`).
    run: str | None = Field(default=None, max_length=1000)
    #: Deploy the commit with this message again (`devgrill rollback`), e.g. the one before
    #: the bad deploy.
    rollback_to: str | None = Field(default=None, max_length=80)
    service: ServiceName
    message: str = Field(default="fix", max_length=80)

    @model_validator(mode="after")
    def _one_action(self) -> SolutionStep:
        if sum(bool(a) for a in (self.patch, self.run, self.rollback_to)) != 1:
            raise ValueError("a solution step has exactly one of: patch, run, rollback_to")
        return self


class SolutionSpec(_Strict):
    """`solution/solution.yaml`: the reference fix that `devgrill-content test` applies."""

    schema_: Literal["devgrill/solution@1"] = Field(alias="schema")
    summary: str = Field(max_length=400)
    steps: list[SolutionStep] = Field(min_length=1, max_length=10)


# -------------------------------------------------------------------------------- approach


class ApproachMatch(_Strict):
    """How the debrief recognises this approach in an attempt (rules until phase 6's AI).

    Every given condition must hold: `rollback` (the player rolled a deploy back), `diff` (a
    regular expression over the diffs the player deployed).
    """

    rollback: bool | None = None
    diff: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _something(self) -> ApproachMatch:
        if self.rollback is None and self.diff is None:
            raise ValueError("a match needs rollback or diff")
        if self.diff is not None:
            try:
                re.compile(self.diff)
            except re.error as exc:
                raise ValueError(f"diff is not a valid regular expression: {exc}") from exc
        return self


class ApproachSpec(_Strict):
    """`approaches/<key>.yaml`: a known way to fix the scenario and how well it does.

    `devgrill-content test --approaches` applies `steps` to a broken sandbox and checks that
    verify gives the declared outcome: `full` passes every probe, `partial` fails exactly
    `fails_probes`, `fails` fails at least those. Cheats (`cheat: true`) are fake fixes and
    tampering attempts that must fail verify; they are never shown to players.
    """

    schema_: Literal["devgrill/approach@1"] = Field(alias="schema")
    key: Slug
    name: str = Field(max_length=80)
    outcome: Literal["full", "partial", "fails"]
    idea: str = Field(max_length=600)
    steps: list[SolutionStep] = Field(min_length=1, max_length=10)
    pros: list[str] = Field(default_factory=list, max_length=6)
    cons: list[str] = Field(default_factory=list, max_length=6)
    #: Which probes this approach is expected to fail (for partial/fails outcomes).
    fails_probes: list[Slug] = Field(default_factory=list)
    match: ApproachMatch | None = None
    cheat: bool = False

    @model_validator(mode="after")
    def _consistent(self) -> ApproachSpec:
        if self.outcome == "full" and self.fails_probes:
            raise ValueError("a full approach fails no probes")
        if self.outcome == "partial" and not self.fails_probes:
            raise ValueError("a partial approach names the probes it fails")
        if self.cheat and self.outcome != "fails":
            raise ValueError("a cheat must fail verify")
        return self


# ----------------------------------------------------------------------------------- tracks


#: A primer is a four-minute read: Markdown in content/primers/<track>/<topic>.md.
PRIMER_MAX_CHARS = 6000


class TopicSpec(_Strict):
    slug: Slug
    title: str = Field(max_length=60)
    #: Filled from content/primers/<track>/<topic>.md when that file exists.
    primer: str | None = Field(default=None, max_length=PRIMER_MAX_CHARS)


class TrackSpec(_Strict):
    slug: Slug
    title: str = Field(max_length=60)
    icon: ServiceKind
    summary: str = Field(max_length=200)
    status: TrackStatus = TrackStatus.PUBLISHED
    topics: list[TopicSpec] = Field(default_factory=list)


class TracksFile(_Strict):
    tracks: list[TrackSpec]


# --------------------------------------------------------------------------- Quick Fire

OptionKey = Literal["a", "b", "c", "d"]
QuickfireLevel = Literal["warmup", "core", "hard"]
#: A card's starting difficulty (Glicko rating), from its level; play moves it from there.
LEVEL_RATING: dict[QuickfireLevel, float] = {"warmup": 1300.0, "core": 1500.0, "hard": 1700.0}


class QuickfireOption(_Strict):
    key: OptionKey
    text: str = Field(min_length=1, max_length=80)


class QuickfireCardSpec(_Strict):
    """One Quick Fire card (content/quickfire/<track>.yaml): evidence, a question, one answer.

    Sized for a phone: short lines of evidence, three or four short options.
    """

    slug: Slug
    kind: QuickfireKind
    level: QuickfireLevel = "core"
    prompt: str = Field(min_length=10, max_length=140)
    evidence: list[Annotated[str, Field(max_length=72)]] = Field(min_length=2, max_length=10)
    options: list[QuickfireOption] = Field(min_length=3, max_length=4)
    answer: OptionKey
    explanation: str = Field(min_length=20, max_length=400)

    @model_validator(mode="after")
    def _one_answer(self) -> QuickfireCardSpec:
        keys = [o.key for o in self.options]
        if keys != ["a", "b", "c", "d"][: len(keys)]:
            raise ValueError("option keys must be a, b, c (and d), in order")
        if self.answer not in keys:
            raise ValueError(f"answer {self.answer!r} is not one of the options")
        if not self.prompt.rstrip().endswith("?"):
            raise ValueError("the prompt is a question: end it with '?'")
        return self


class QuickfireFile(_Strict):
    cards: list[QuickfireCardSpec] = Field(min_length=1)
