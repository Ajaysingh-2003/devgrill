"""Turn Prometheus scrapes into the named metrics a base app declares (gauge, rate, ratio,
quantile). Pure functions: the driver supplies the scrape text, callers keep the history.

Only the Prometheus text exposition format is parsed; that is all the exporters emit.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from devgrill.sandbox.baseapp import MetricDef

_SAMPLE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?\s+(\S+)(?:\s+\d+)?$")
_LABEL = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


@dataclass(frozen=True, slots=True)
class Sample:
    name: str
    labels: dict[str, str]
    value: float


@dataclass(slots=True)
class Scrape:
    """One scrape of every job at time `t` (seconds, any monotonic origin)."""

    t: float
    samples: dict[str, list[Sample]] = field(default_factory=dict)


def parse_text(text: str) -> list[Sample]:
    samples: list[Sample] = []
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _SAMPLE.match(line.strip())
        if not match:
            continue
        name, raw_labels, raw_value = match.groups()
        try:
            value = float(raw_value)
        except ValueError:
            continue
        labels = {
            k: v.replace('\\"', '"').replace("\\\\", "\\")
            for k, v in _LABEL.findall(raw_labels or "")
        }
        samples.append(Sample(name, labels, value))
    return samples


def _matches(sample: Sample, wanted: Mapping[str, str]) -> bool:
    return all(re.fullmatch(pattern, sample.labels.get(key, "")) for key, pattern in wanted.items())


def _sum(samples: Iterable[Sample], name: str, wanted: Mapping[str, str]) -> float | None:
    values = [s.value for s in samples if s.name == name and _matches(s, wanted)]
    return sum(values) if values else None


def _increase(
    prev: Scrape, cur: Scrape, job: str, name: str, wanted: Mapping[str, str]
) -> float | None:
    before = _sum(prev.samples.get(job, []), name, wanted)
    after = _sum(cur.samples.get(job, []), name, wanted)
    if after is None:
        return None
    if before is None or after < before:  # first sight, or the process restarted
        return None
    return after - before


def _buckets(
    scrape: Scrape, job: str, metric: str, wanted: Mapping[str, str]
) -> dict[float, float]:
    out: dict[float, float] = {}
    for s in scrape.samples.get(job, []):
        if s.name != f"{metric}_bucket" or not _matches(s, wanted):
            continue
        le = s.labels.get("le", "")
        bound = math.inf if le == "+Inf" else float(le)
        out[bound] = out.get(bound, 0.0) + s.value
    return out


def _quantile(q: float, buckets: dict[float, float]) -> float | None:
    """histogram_quantile over cumulative bucket counts (linear interpolation, like Prometheus)."""
    if not buckets:
        return None
    bounds = sorted(buckets)
    total = buckets[bounds[-1]]
    if total <= 0:
        return None
    rank = q * total
    prev_bound, prev_count = 0.0, 0.0
    for bound in bounds:
        count = buckets[bound]
        if count >= rank:
            if math.isinf(bound):
                return prev_bound
            if count == prev_count:
                return bound
            return prev_bound + (bound - prev_bound) * (rank - prev_count) / (count - prev_count)
        prev_bound, prev_count = bound, count
    return prev_bound


def evaluate(definition: MetricDef, prev: Scrape | None, cur: Scrape) -> float | None:
    """The metric's value now; None when it can't be known yet (no traffic, first scrape)."""
    job, name = definition.job, definition.metric
    if definition.type == "gauge":
        value = _sum(cur.samples.get(job, []), name, definition.labels)
        return None if value is None else value * definition.scale
    if prev is None or cur.t <= prev.t:
        return None
    elapsed = cur.t - prev.t
    if definition.type == "rate":
        inc = _increase(prev, cur, job, name, definition.labels)
        return None if inc is None else inc / elapsed * definition.scale
    if definition.type == "ratio":
        whole = _increase(prev, cur, job, name, {})
        if whole is None or whole <= 0:
            return None  # no traffic: the ratio is unknown, not zero
        # A label value never seen (no 5xx yet) has no series at all: that part is zero.
        part = _increase(prev, cur, job, name, definition.labels) or 0.0
        return part / whole * definition.scale
    # quantile over the observations between the two scrapes
    before = _buckets(prev, job, name, definition.labels)
    after = _buckets(cur, job, name, definition.labels)
    delta = {b: after[b] - before.get(b, 0.0) for b in after}
    if any(v < 0 for v in delta.values()):
        return None
    assert definition.q is not None
    value = _quantile(definition.q, delta)
    return None if value is None else value * definition.scale


def evaluate_all(
    definitions: Mapping[str, MetricDef], prev: Scrape | None, cur: Scrape
) -> dict[str, float | None]:
    return {key: evaluate(d, prev, cur) for key, d in definitions.items()}
