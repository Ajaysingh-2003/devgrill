"""Which approach did the player take? (ADR 016, PLAN §13.2.4)

The scenario's `match` rules (devgrill.domain.debrief) answer first: cheap and certain. When
none matches, the change goes to the judge model with the known approaches ranked by embedding
similarity, the deployed diff and the verify results; it answers with a known key or
"unknown". Unknown changes become candidates for the admin review queue, where similar ones
are grouped (cosine similarity) and can be promoted to known approaches.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from devgrill.ai.port import CallMeta, Llm
from devgrill.ai.registry import prompt
from devgrill.ai.safety import DATA_POLICY, fence

UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Known:
    key: str
    name: str
    idea: str
    outcome: str
    vector: Sequence[float] | None = None


class ClassifyOutput(BaseModel):
    key: str
    confidence: float = Field(ge=0, le=1)
    rationale: str


@dataclass(frozen=True, slots=True)
class Classification:
    key: str
    confidence: float
    rationale: str

    @property
    def known(self) -> bool:
        return self.key != UNKNOWN


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rank(
    known: Sequence[Known], vector: Sequence[float] | None
) -> list[tuple[Known, float | None]]:
    if vector is None:
        return [(k, None) for k in known]
    scored = [(k, cosine(k.vector, vector) if k.vector else None) for k in known]
    return sorted(scored, key=lambda kv: -(kv[1] if kv[1] is not None else -1.0))


def describe(known: Known) -> str:
    return f"{known.name}: {known.idea} (verify outcome: {known.outcome})"


def groups(vectors: Sequence[Sequence[float]], threshold: float = 0.85) -> list[list[int]]:
    """Greedy clusters of similar unknown changes (indexes), for the admin queue."""
    out: list[list[int]] = []
    for i, v in enumerate(vectors):
        for cluster in out:
            if cosine(vectors[cluster[0]], v) >= threshold:
                cluster.append(i)
                break
        else:
            out.append([i])
    return out


async def classify(
    llm: Llm,
    *,
    title: str,
    known: Sequence[Known],
    diff: str,
    actions: str,
    probes: Sequence[str],
    vector: Sequence[float] | None,
    meta: CallMeta,
) -> Classification:
    ranked = rank(known, vector)
    approaches = "\n".join(
        f"- {k.key}: {describe(k)}" + (f" (similarity {s:.2f})" if s is not None else "")
        for k, s in ranked
    )
    out = await llm.parse(
        prompt("classify"),
        {
            "title": title,
            "approaches": approaches or "(none known yet)",
            "diff": fence("diff", diff or "(no code or config deployed)", limit=12000),
            "actions": actions,
            "probes": "\n".join(probes) or "(no verify run)",
            "data_policy": DATA_POLICY,
        },
        ClassifyOutput,
        meta,
    )
    if out.key == UNKNOWN or out.key in {k.key for k in known}:
        return Classification(out.key, out.confidence, out.rationale.strip())
    # A key that doesn't exist is not an answer: unknown, with no confidence.
    return Classification(UNKNOWN, 0.0, out.rationale.strip())
