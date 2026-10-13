"""Closed vocabularies shared by the database, the API and the UI.

Values are the wire and database spelling. Postgres enum types are created from these classes
(see devgrill.infra.models), so adding a member needs a migration.
"""

from __future__ import annotations

from enum import StrEnum


class Difficulty(StrEnum):
    """Severity of an incident. SEV1 is the hardest."""

    SEV4 = "sev4"
    SEV3 = "sev3"
    SEV2 = "sev2"
    SEV1 = "sev1"


class ScenarioStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    RETIRED = "retired"


class ScenarioSource(StrEnum):
    HANDWRITTEN = "handwritten"
    GENERATED = "generated"
    COMMUNITY = "community"
    POSTMORTEM_REPLAY = "postmortem_replay"


class TrackStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


class FaultKind(StrEnum):
    CODE_PATCH = "code_patch"
    CONFIG = "config"
    TOXIC = "toxic"
    RESOURCE = "resource"
    DATA = "data"
    INFRA = "infra"


class ProbeKind(StrEnum):
    LOAD = "load"
    CHAOS = "chaos"
    INVARIANT = "invariant"
    HIDDEN_TEST = "hidden_test"
    BUDGET = "budget"


class ApproachOutcome(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    FAILS = "fails"


class QuickfireKind(StrEnum):
    LOG = "log"
    GRAPH = "graph"
    DIFF = "diff"
    CONFIG = "config"


class AttemptMode(StrEnum):
    TUTORIAL = "tutorial"
    GUIDED = "guided"
    ONCALL = "oncall"
    DAILY = "daily"
    WEEKLY = "weekly"


class AttemptState(StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    MITIGATED = "mitigated"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"
    EXPIRED = "expired"
    FAILED = "failed"


class SandboxDriver(StrEnum):
    COMPOSE = "compose"
    SYSBOX = "sysbox"
    FIRECRACKER = "firecracker"
    HOSTED = "hosted"


class AuthorKind(StrEnum):
    USER = "user"
    PERSONA = "persona"
    SYSTEM = "system"


class VerifyStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    PARTIAL = "partial"
    FAILED = "failed"
    ERROR = "error"


class ExperienceLevel(StrEnum):
    STUDENT = "student"
    Y0_2 = "0-2"
    Y2_5 = "2-5"
    Y5_PLUS = "5+"


class Role(StrEnum):
    USER = "user"
    AUTHOR = "author"
    REVIEWER = "reviewer"
    ADMIN = "admin"


class Plan(StrEnum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"


class ChallengeKind(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class StreakMode(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


class CohortRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"
