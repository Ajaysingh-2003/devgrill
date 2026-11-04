"""Case files (ADR 013, ADR 018): deterministic scoring, and what the evidence must show.

The player names the root cause, the first mitigation and the durable fix. Naming the cause
is worth the most: the other two follow from it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from devgrill.domain.spec import (
    CaseClue,
    CaseEvidence,
    CaseFileSpec,
    CaseOption,
    CaseQuestion,
    OptionKey,
)

QuestionKey = Literal["root_cause", "mitigation", "fix"]
QUESTION_KEYS: tuple[QuestionKey, ...] = ("root_cause", "mitigation", "fix")
PROMPTS: Mapping[QuestionKey, str] = {
    "root_cause": "What caused this?",
    "mitigation": "What do you do first, to get customers working again?",
    "fix": "What is the durable fix?",
}
WEIGHTS: Mapping[QuestionKey, int] = {"root_cause": 50, "mitigation": 25, "fix": 25}


@dataclass(frozen=True, slots=True)
class CaseAnswer:
    key: QuestionKey
    choice: str
    correct: bool
    answer: OptionKey
    explanation: str


@dataclass(frozen=True, slots=True)
class CaseScore:
    score: int
    answers: tuple[CaseAnswer, ...]


def question(spec: CaseFileSpec, key: QuestionKey) -> CaseQuestion:
    found: CaseQuestion = getattr(spec, key)
    return found


def score(spec: CaseFileSpec, choices: Mapping[str, str]) -> CaseScore:
    """0 to 100 from the three answers; the same answers always score the same."""
    answers: list[CaseAnswer] = []
    total = 0
    for key in QUESTION_KEYS:
        q = question(spec, key)
        correct = choices[key] == q.answer
        total += WEIGHTS[key] if correct else 0
        answers.append(CaseAnswer(key, choices[key], correct, q.answer, q.explanation))
    return CaseScore(total, tuple(answers))


def shuffled(slug: str, key: QuestionKey, options: Sequence[CaseOption]) -> list[CaseOption]:
    """A stable order per case and question, so where an author put the answer says nothing."""

    def rank(option: CaseOption) -> str:
        return hashlib.sha256(f"{slug}:{key}:{option.key}".encode()).hexdigest()

    return sorted(options, key=rank)


def panel_text(evidence: CaseEvidence, panel: str) -> str:
    """Everything one panel shows of the recording, as text to search."""
    parts: list[object]
    match panel:
        case "deploys":
            parts = [evidence.deploys, *(c.get("diff") for c in evidence.changes.values())]
        case "logs":
            parts = [line.line for line in evidence.logs]
        case "database":
            parts = [evidence.db]
        case "cache":
            parts = [evidence.cache]
        case "code":
            parts = [text for files in evidence.files.values() for text in files.values()]
        case _:
            parts = [c.output for c in evidence.commands]
    return "\n".join(p if isinstance(p, str) else json.dumps(p, ensure_ascii=False) for p in parts)


def missing_clues(spec: CaseFileSpec, evidence: CaseEvidence) -> list[CaseClue]:
    """The clues this recording doesn't show: the questions wouldn't be fair on it."""
    return [c for c in spec.clues if c.contains not in panel_text(evidence, c.panel)]
