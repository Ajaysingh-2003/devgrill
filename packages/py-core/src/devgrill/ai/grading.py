"""Postmortem grading (ADR 016, PLAN §13.2.3).

The judge model scores each rubric criterion using its anchors, quotes the postmortem as
evidence, checks blamelessness and writes feedback. The result is then checked here, so a
grade can't rest on things the author never wrote:
- evidence must be found word for word in the postmortem (ignoring case, quotes and spaces);
- a positive score whose evidence all fails that check is halved (rounded down) and flagged;
- scores are clamped to the criterion's range, unknown criteria dropped, missing ones scored 0;
- a postmortem that blames people loses 20% of its fraction (it still gets feedback).

`fraction` (0..1) is the score's postmortem component (devgrill.domain.scoring).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from pydantic import BaseModel, Field

from devgrill.ai.port import CallMeta, Llm
from devgrill.ai.registry import prompt
from devgrill.ai.safety import DATA_POLICY, fence
from devgrill.domain.spec import RubricCriterion

BLAME_FACTOR: Final = 0.8


class CriterionGrade(BaseModel):
    key: str
    score: int
    evidence: list[str] = Field(default_factory=list)
    reason: str


class GradeOutput(BaseModel):
    criteria: list[CriterionGrade]
    blameless: bool
    blame: list[str] = Field(default_factory=list)
    feedback: str


@dataclass(frozen=True, slots=True)
class Facts:
    root_cause: str
    timeline: Sequence[str]
    probes: Sequence[str]
    approach: str | None = None


@dataclass
class CriterionResult:
    key: str
    score: int
    max: int
    evidence: list[str]
    reason: str
    unsupported: bool = False


@dataclass
class Grade:
    criteria: list[CriterionResult]
    blameless: bool
    blame: list[str]
    feedback: str
    total: int = field(init=False)
    max_total: int = field(init=False)

    def __post_init__(self) -> None:
        self.total = sum(c.score for c in self.criteria)
        self.max_total = sum(c.max for c in self.criteria)

    @property
    def fraction(self) -> float:
        if not self.max_total:
            return 0.0
        base = self.total / self.max_total
        return round(base * (1.0 if self.blameless else BLAME_FACTOR), 4)

    def as_dict(self) -> dict[str, object]:
        return {
            "criteria": [
                {
                    "key": c.key,
                    "score": c.score,
                    "max": c.max,
                    "evidence": c.evidence,
                    "reason": c.reason,
                    "unsupported": c.unsupported,
                }
                for c in self.criteria
            ],
            "blameless": self.blameless,
            "blame": self.blame,
            "total": self.total,
            "max": self.max_total,
            "fraction": self.fraction,
        }


# Typographic quotes and dashes fold to plain ones (models and people mix them).
_FOLD = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})  # noqa: RUF001


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.translate(_FOLD)).strip().lower()


def quoted(quote: str, document: str) -> bool:
    """Is `quote` really in the document (ignoring case, quote style and spacing)?"""
    q = _norm(quote).strip("\"' .…")
    return bool(q) and q in _norm(document)


def check(output: GradeOutput, rubric: Sequence[RubricCriterion], postmortem: str) -> Grade:
    by_key = {c.key: c for c in output.criteria}
    results: list[CriterionResult] = []
    for criterion in rubric:
        got = by_key.get(criterion.key)
        if got is None:
            results.append(CriterionResult(criterion.key, 0, criterion.max, [], "not graded"))
            continue
        score = max(0, min(criterion.max, got.score))
        evidence = [q for q in got.evidence if quoted(q, postmortem)]
        unsupported = score > 0 and not evidence
        if unsupported:
            score //= 2
        results.append(
            CriterionResult(criterion.key, score, criterion.max, evidence, got.reason, unsupported)
        )
    blame = [q for q in output.blame if quoted(q, postmortem)]
    # Blame only counts with a real quote: no quote, no penalty.
    blameless = output.blameless or not blame
    return Grade(results, blameless, blame, output.feedback.strip())


def rubric_text(rubric: Sequence[RubricCriterion]) -> str:
    lines = []
    for c in rubric:
        lines.append(f"- {c.key} (0 to {c.max}): {c.description}")
        lines += [f"    {level}: {text}" for level, text in sorted(c.anchors.items())]
    return "\n".join(lines)


def facts_text(facts: Facts) -> str:
    parts = [f"Root cause: {facts.root_cause}"]
    if facts.approach:
        parts.append(f"How the player fixed it: {facts.approach}")
    if facts.timeline:
        parts.append("Timeline from the session:\n" + "\n".join(facts.timeline[-30:]))
    if facts.probes:
        parts.append("Verify results:\n" + "\n".join(facts.probes))
    return "\n\n".join(parts)


async def grade(
    llm: Llm,
    rubric: Sequence[RubricCriterion],
    facts: Facts,
    postmortem: str,
    meta: CallMeta,
) -> Grade:
    output = await llm.parse(
        prompt("grade"),
        {
            "rubric": rubric_text(rubric),
            "facts": facts_text(facts),
            "postmortem": fence("postmortem", postmortem, limit=16000),
            "data_policy": DATA_POLICY,
        },
        GradeOutput,
        meta,
    )
    return check(output, rubric, postmortem)
