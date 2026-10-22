"""Guiding the player (ADR 016, PLAN §13.2.2 and §13.2.5).

- **Nudge** (guided mode): one or two sentences that move the player toward the next authored
  hint without quoting it, from their last 20 trail events. Checked against the scenario's
  spoilers like a teammate's reply.
- **Coach note** (the debrief): one paragraph on where time went and the clue that mattered.
  It cites trail events by id; citations of ids that aren't in the trail are removed, so the
  note can point at the replay without inventing anything.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from devgrill.ai.port import AiUnavailable, CallMeta, Llm
from devgrill.ai.registry import prompt
from devgrill.ai.safety import DATA_POLICY, claims_action, fence, leaks


class NudgeOutput(BaseModel):
    nudge: str


async def nudge(
    llm: Llm,
    *,
    title: str,
    story: str,
    direction: str,
    trail: Sequence[str],
    spoilers: Sequence[str],
    meta: CallMeta,
) -> str:
    out = await llm.parse(
        prompt("nudge"),
        {
            "title": title,
            "story": story,
            "direction": direction,
            "trail": fence("trail", "\n".join(trail[-20:]) or "(nothing yet)"),
            "data_policy": DATA_POLICY,
        },
        NudgeOutput,
        meta,
    )
    text = out.nudge.strip()
    if leaks(text, spoilers) or claims_action(text):
        raise AiUnavailable("error", "the nudge gave too much away")
    return text


# ------------------------------------------------------------------------------- coach


class CoachOutput(BaseModel):
    note: str
    cites: list[int] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TrailLine:
    id: int
    minutes: float
    text: str
    mark: str | None = None

    def render(self) -> str:
        mark = f" [{self.mark}]" if self.mark else ""
        return f"e{self.id} | {self.minutes:+.1f} min | {self.text}{mark}"


@dataclass(frozen=True, slots=True)
class Note:
    text: str
    cites: list[int]


_CITE = re.compile(r"\s*\[e(\d+)\]")


def clean_note(output: CoachOutput, trail: Sequence[TrailLine]) -> Note:
    """Keep only citations of real trail events, in the text and in the list."""
    ids = {line.id for line in trail}

    def keep(match: re.Match[str]) -> str:
        return match.group(0) if int(match.group(1)) in ids else ""

    text = _CITE.sub(keep, output.note).strip()
    cited = [int(i) for i in _CITE.findall(text)]
    cites = sorted({c for c in output.cites if c in ids} | set(cited))
    return Note(text, cites)


async def coach_note(
    llm: Llm,
    *,
    title: str,
    root_cause: str,
    outcome: str,
    trail: Sequence[TrailLine],
    meta: CallMeta,
) -> Note:
    if not trail:
        raise AiUnavailable("error", "no trail to coach from")
    out = await llm.parse(
        prompt("coach"),
        {
            "title": title,
            "root_cause": root_cause,
            "outcome": outcome,
            "trail": fence("trail", "\n".join(line.render() for line in trail[-60:])),
            "data_policy": DATA_POLICY,
        },
        CoachOutput,
        meta,
    )
    return clean_note(out, trail)
