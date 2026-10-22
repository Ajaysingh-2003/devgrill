"""War-room teammates that answer (ADR 016, PLAN §13.2.1).

Scripted beats stay deterministic; this is what happens when the player writes to the room.
A teammate (the one addressed, else the last one who spoke) replies in a sentence or three,
streamed. The reply is built from the scenario story, the attempt's state, the player's
redacted trail and the hints they have unlocked; never the solution.

Guardrails, in order:
1. While streaming, a reply that starts giving away the root cause (the scenario's
   `ai.spoilers`, before hint `ai.reveal_at`) or claims an action is cut and retracted.
2. A finished reply is checked again, and for SEV1 scenarios also by a second model call.
3. A withheld reply is replaced by a safe line in the teammate's voice. Nothing is retried in a
   loop: a teammate who can't answer safely asks the player to look at the evidence.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from devgrill.ai.port import CallMeta, Llm
from devgrill.ai.registry import prompt
from devgrill.ai.safety import DATA_POLICY, claims_action, fence, leaks


@dataclass(frozen=True, slots=True)
class Persona:
    slug: str
    name: str
    role: str
    voice: str
    #: What they say when their own reply was withheld (still useful, never a spoiler).
    safe_line: str


PERSONAS: dict[str, Persona] = {
    "priya": Persona(
        "priya",
        "Priya",
        "product manager",
        "Calm and business-minded. You care about customers, the sale, status updates and"
        " ETAs, and you translate tech-speak into impact. You aren't deeply technical.",
        "I can't judge the technical side. What are the graphs telling you, and what should I"
        " tell customers in the meantime?",
    ),
    "arjun": Persona(
        "arjun",
        "Arjun",
        "SRE",
        "Hands-on and terse. You think in signals: dashboards, logs, recent changes. You"
        " suggest where to look and ask sharp questions, and you push back on guesses.",
        "Not sure yet. What changed recently, and which signal moved first?",
    ),
}
DEFAULT_PERSONA = "arjun"


@dataclass(frozen=True, slots=True)
class Context:
    title: str
    story: str
    page: str
    state: str
    minutes: int
    #: Texts of the hints the player has taken, tier 1 first.
    hints: Sequence[str]
    #: The player's trail as one line per event (already redacted text is fine).
    trail: Sequence[str]
    #: (speaker, text), oldest first; "You" is the player.
    conversation: Sequence[tuple[str, str]]
    spoilers: Sequence[str] = ()
    reveal_at: int = 3
    severity: str = "SEV3"
    root_cause: str = ""
    personas: Sequence[str] = field(default_factory=lambda: list(PERSONAS))


def choose(text: str, conversation: Sequence[tuple[str, str]], available: Sequence[str]) -> Persona:
    """The teammate addressed by name (or @name), else the last one who spoke, else the SRE."""
    pool = [PERSONAS[p] for p in available if p in PERSONAS] or list(PERSONAS.values())
    for persona in pool:
        if re.search(rf"(?<![\w@])@?{re.escape(persona.name)}\b", text, re.I):
            return persona
    for speaker, _ in reversed(conversation):
        for persona in pool:
            if speaker == persona.name:
                return persona
    return next((p for p in pool if p.slug == DEFAULT_PERSONA), pool[0])


def spoilers_locked(ctx: Context) -> Sequence[str]:
    """The spoiler patterns still off-limits for this player (none once they reached reveal_at)."""
    return () if len(ctx.hints) >= ctx.reveal_at else ctx.spoilers


def violations(text: str, ctx: Context) -> list[str]:
    found = [f"spoiler: {t}" for t in leaks(text, spoilers_locked(ctx))]
    if claims_action(text):
        found.append("claims an action")
    return found


def values(ctx: Context, persona: Persona) -> dict[str, str]:
    taken = [f"Hint {i}: {h}" for i, h in enumerate(ctx.hints, 1)]
    hint_rule = (
        "The player has unlocked these hints. You may build on them, but never go further:\n"
        + "\n".join(taken)
        if taken
        else "The player hasn't taken any hints. Don't point them further than what they've"
        " already noticed themselves."
    )
    conversation = "\n".join(f"{who}: {what}" for who, what in ctx.conversation[-12:])
    return {
        "name": persona.name,
        "role": persona.role,
        "voice": persona.voice,
        "hint_rule": hint_rule,
        "data_policy": DATA_POLICY,
        "title": ctx.title,
        "story": ctx.story,
        "page": ctx.page,
        "state": ctx.state,
        "minutes": str(ctx.minutes),
        "trail": fence("trail", "\n".join(ctx.trail[-20:]) or "(nothing yet)"),
        "conversation": fence("war-room", conversation or "(no messages yet)"),
    }


class SelfCheck(BaseModel):
    reveals: bool
    reason: str


@dataclass
class Outcome:
    text: str
    withheld: list[str] = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return not self.withheld


Event = tuple[Literal["delta", "reset"], str]


async def reply(llm: Llm, ctx: Context, persona: Persona, meta: CallMeta) -> AsyncIterator[Event]:
    """Stream a reply as ("delta", text) events; ("reset", why) retracts what was streamed.

    The last event's accumulated text is the reply. Raises AiUnavailable before the first
    event when AI can't answer at all.
    """
    text, cut = "", False
    async for delta in llm.stream(prompt("persona"), values(ctx, persona), meta):
        text += delta
        cut = cut or bool(violations(text, ctx))
        if not cut:  # stop showing it the moment it goes wrong; read the rest (it's metered)
            yield ("delta", delta)
    problems = violations(text, ctx)
    if not problems and ctx.severity == "SEV1" and spoilers_locked(ctx) and ctx.root_cause:
        check = await llm.parse(
            prompt("selfcheck"),
            {
                "root_cause": ctx.root_cause,
                "reply": fence("reply", text),
                "data_policy": DATA_POLICY,
            },
            SelfCheck,
            CallMeta("selfcheck", meta.user_id, meta.attempt_id),
        )
        if check.reveals:
            problems.append(f"self-check: {check.reason[:200]}")
    if problems:
        yield ("reset", "; ".join(problems))
        yield ("delta", persona.safe_line)


async def collect(llm: Llm, ctx: Context, persona: Persona, meta: CallMeta) -> Outcome:
    """The whole reply (evals, non-streaming callers)."""
    text, withheld = "", []
    async for kind, value in reply(llm, ctx, persona, meta):
        if kind == "reset":
            text, withheld = "", [value]
        else:
            text += value
    return Outcome(text.strip(), withheld)
