"""The LLM port (ADR 016): what AI features need from a model, and nothing about OpenAI.

`devgrill.infra.llm.OpenAiLlm` implements it with the Responses API, budgets, metering and
tracing. `FakeLlm` answers from scripted replies, for tests (and as the "AI off" mode).

Every call names its feature (for budgets, caps and the cost dashboard) and who it was for.
When AI can't answer (off, over budget, over a plan's allowance, or erroring after retries and
the fallback model) the call raises `AiUnavailable`, and the feature degrades: teammates go
quiet and point at the authored hints, a postmortem waits for review, the debrief has no note.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel

from devgrill.ai.registry import Prompt

Feature = Literal["persona", "nudge", "grade", "classify", "coach", "selfcheck", "embed"]
Unavailable = Literal["disabled", "budget", "limit", "error"]


class AiUnavailable(Exception):  # noqa: N818 - it's a state, not a bug
    def __init__(self, reason: Unavailable, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True, slots=True)
class CallMeta:
    feature: Feature
    user_id: uuid.UUID | None = None
    attempt_id: uuid.UUID | None = None
    #: The llm_calls row id of the successful call (so a war-room message can point at it).
    call_id: uuid.UUID = field(default_factory=uuid.uuid4)


class Llm(Protocol):
    def enabled(self, feature: Feature) -> bool: ...

    async def parse[T: BaseModel](
        self, prompt: Prompt, values: Mapping[str, str], schema: type[T], meta: CallMeta
    ) -> T: ...

    def stream(
        self, prompt: Prompt, values: Mapping[str, str], meta: CallMeta
    ) -> AsyncIterator[str]: ...

    async def embed(self, texts: list[str], meta: CallMeta) -> list[list[float]]: ...


Reply = str | BaseModel | Callable[[str, str], str | BaseModel] | Exception


@dataclass
class FakeLlm:
    """Scripted answers by prompt name. A callable gets (instructions, input) and returns the
    answer; an exception is raised. With no script for a prompt, the call is unavailable."""

    replies: dict[str, list[Reply]] = field(default_factory=dict)
    disabled: set[str] = field(default_factory=set)
    calls: list[tuple[str, CallMeta, str, str]] = field(default_factory=list)
    vector: Callable[[str], list[float]] | None = None

    def enabled(self, feature: Feature) -> bool:
        return feature not in self.disabled

    def _next(self, prompt: Prompt, values: Mapping[str, str], meta: CallMeta) -> Any:
        if not self.enabled(meta.feature):
            raise AiUnavailable("disabled", meta.feature)
        instructions, user = prompt.render(**values)
        self.calls.append((prompt.name, meta, instructions, user))
        queue = self.replies.get(prompt.name)
        if not queue:
            raise AiUnavailable("error", f"no scripted reply for {prompt.name}")
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return reply(instructions, user) if callable(reply) else reply

    async def parse[T: BaseModel](
        self, prompt: Prompt, values: Mapping[str, str], schema: type[T], meta: CallMeta
    ) -> T:
        reply = self._next(prompt, values, meta)
        return reply if isinstance(reply, schema) else schema.model_validate(reply)

    async def stream(
        self, prompt: Prompt, values: Mapping[str, str], meta: CallMeta
    ) -> AsyncIterator[str]:
        text = str(self._next(prompt, values, meta))
        for i in range(0, len(text), 8):
            yield text[i : i + 8]

    async def embed(self, texts: list[str], meta: CallMeta) -> list[list[float]]:
        if not self.enabled("embed"):
            raise AiUnavailable("disabled", "embed")
        fn = self.vector or (lambda s: [float(len(s) % 7), float(s.count(" ") % 5), 1.0])
        return [fn(t) for t in texts]
