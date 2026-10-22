"""The eval harness: the real OpenAI adapter, metered in memory instead of Postgres, plus the
small statistics the gates need."""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from devgrill.ai.port import CallMeta
from devgrill.ai.pricing import cost_usd
from devgrill.config import Settings
from devgrill.domain.spec import ScenarioSpec
from devgrill.infra.llm import OpenAiLlm
from devgrill.sandbox.content import Bundle, load_approaches, load_bundle

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT.parent / "content"
REPORTS = ROOT / "reports"


@dataclass
class Metered:
    feature: str
    model: str
    prompt: str
    cost: Decimal
    latency_ms: int
    status: str


class EvalLlm(OpenAiLlm):
    """OpenAiLlm with its spend kept in memory (evals have no database)."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings, None)  # type: ignore[arg-type]
        self.calls: list[Metered] = []

    async def spent_today(self, now: datetime | None = None) -> Decimal:
        return sum((c.cost for c in self.calls), Decimal(0))

    async def _meter(
        self,
        meta: CallMeta,
        prompt_id: str,
        model: str,
        usage: Any,
        started: float,
        status: str,
        trace_id: str | None,
    ) -> None:
        details = getattr(usage, "input_tokens_details", None)
        self.calls.append(
            Metered(
                feature=meta.feature,
                model=model,
                prompt=prompt_id,
                cost=cost_usd(
                    model,
                    input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                    cached_tokens=int(getattr(details, "cached_tokens", 0) or 0),
                    output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
                ),
                latency_ms=round((time.perf_counter() - started) * 1000),
                status=status,
            )
        )

    def cost(self, feature: str | None = None) -> Decimal:
        return sum(
            (c.cost for c in self.calls if feature is None or c.feature == feature), Decimal(0)
        )


def load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), path
    return data


_bundles: dict[str, Bundle] = {}


def bundle(slug: str) -> Bundle:
    if slug not in _bundles:
        _bundles[slug] = load_bundle(CONTENT, slug)
    return _bundles[slug]


def spec(slug: str) -> ScenarioSpec:
    return bundle(slug).scenario


def known_approaches(slug: str) -> list[tuple[str, str, str, str]]:
    """(key, name, idea, outcome) of the approaches players can be told about (no cheats)."""
    return [
        (a.key, a.name, a.idea, a.outcome) for _, a in load_approaches(bundle(slug)) if not a.cheat
    ]


# ---------------------------------------------------------------------------- statistics


def percentile(values: Sequence[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100)."""
    if not values:
        return None
    ordered = sorted(values)
    k = max(0, math.ceil(q / 100 * len(ordered)) - 1)
    return ordered[k]


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Spearman's rho (Pearson on average ranks); None when either side is constant."""
    if len(a) != len(b) or len(a) < 3:
        return None
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return cov / (va * vb) if va and vb else None
