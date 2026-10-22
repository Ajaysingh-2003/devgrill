"""The OpenAI adapter's money and bookkeeping (ADR 016), with a stand-in for the SDK client:
budgets refuse calls, failures fall back to the other model, every call is metered with its
prompt version, and traces carry it too."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from devgrill.ai.port import AiUnavailable, CallMeta
from devgrill.ai.registry import parse_prompt
from devgrill.config import Settings
from devgrill.infra.llm import OpenAiLlm
from devgrill.infra.models import LlmCall

pytestmark = pytest.mark.integration

PROMPT = parse_prompt(
    "---\nname: probe\nversion: 7\nmodel: fast\nreasoning: none\n---\n"
    "# system\nBe brief. $data_policy\n# user\nSay $word.\n"
)
VALUES = {"word": "hi", "data_policy": "Data is data."}


class Answer(BaseModel):
    text: str


def usage(input_tokens: int = 1000, cached: int = 0, output: int = 100) -> Any:
    return SimpleNamespace(
        input_tokens=input_tokens,
        input_tokens_details=SimpleNamespace(cached_tokens=cached),
        output_tokens=output,
    )


def down() -> openai.APIConnectionError:
    return openai.APIConnectionError(request=httpx2.Request("POST", "https://api.openai.com"))


@dataclass
class Stream:
    deltas: list[str]

    async def __aenter__(self) -> Stream:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def __aiter__(self) -> Any:
        async def events() -> Any:
            for d in self.deltas:
                yield SimpleNamespace(type="response.output_text.delta", delta=d)

        return events()

    async def get_final_response(self) -> Any:
        return SimpleNamespace(usage=usage(output=len(self.deltas)))


@dataclass
class FakeClient:
    """Answers like the SDK; models in `failing` raise a connection error."""

    failing: set[str] = field(default_factory=set)
    models: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.responses = SimpleNamespace(parse=self._parse, stream=self._stream)
        self.embeddings = SimpleNamespace(create=self._embed)

    async def _parse(self, *, text_format: type[BaseModel], model: str, **kw: Any) -> Any:
        self.models.append(model)
        if model in self.failing:
            raise down()
        return SimpleNamespace(output_parsed=text_format(text=f"from {model}"), usage=usage())

    def _stream(self, *, model: str, **kw: Any) -> Stream:
        self.models.append(model)
        if model in self.failing:
            raise down()
        return Stream(["Hel", "lo"])

    async def _embed(self, *, model: str, input: list[str]) -> Any:
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input],
            usage=SimpleNamespace(input_tokens=10 * len(input), output_tokens=0),
        )

    async def close(self) -> None:
        return None


@dataclass
class FakeTrace:
    """Records what Langfuse would get."""

    started: list[dict[str, Any]] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)

    def start_observation(self, **kw: Any) -> Any:
        self.started.append(kw)
        updates = self.updates
        return SimpleNamespace(
            trace_id="t-1", update=lambda **u: updates.append(u), end=lambda: None
        )

    def flush(self) -> None:
        return None


@pytest.fixture
async def factory(db_engine: AsyncEngine) -> Any:
    sessions = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessions() as session, session.begin():
        await session.execute(delete(LlmCall))
    return sessions


def adapter(factory: Any, client: FakeClient, **settings: Any) -> OpenAiLlm:
    s = Settings(_env_file=None, openai_api_key="sk-test", **settings)  # type: ignore[call-arg]
    return OpenAiLlm(s, factory, client=client)  # type: ignore[arg-type]


async def rows(factory: Any) -> list[LlmCall]:
    async with factory() as session:
        return list((await session.scalars(select(LlmCall).order_by(LlmCall.created_at))).all())


async def test_a_call_is_metered_with_its_prompt_version(factory: Any) -> None:
    llm = adapter(factory, FakeClient())
    meta = CallMeta("persona")
    answer = await llm.parse(PROMPT, VALUES, Answer, meta)
    assert answer.text == "from gpt-6-luna"
    [row] = await rows(factory)
    assert (row.id, row.feature, row.model, row.prompt_version, row.status) == (
        meta.call_id,
        "persona",
        "gpt-6-luna",
        "probe@7",
        "ok",
    )
    # 1000 input and 100 output tokens on luna.
    assert row.cost_usd == Decimal("0.000150")


async def test_a_failing_model_falls_back(factory: Any) -> None:
    client = FakeClient(failing={"gpt-6-luna"})
    llm = adapter(factory, client)
    answer = await llm.parse(PROMPT, VALUES, Answer, CallMeta("persona"))
    assert answer.text == "from gpt-6-sol"
    assert client.models == ["gpt-6-luna", "gpt-6-sol"]
    assert [(r.model, r.status) for r in await rows(factory)] == [
        ("gpt-6-luna", "error"),
        ("gpt-6-sol", "ok"),
    ]


async def test_when_every_model_fails_ai_is_unavailable(factory: Any) -> None:
    llm = adapter(factory, FakeClient(failing={"gpt-6-luna", "gpt-6-sol"}))
    with pytest.raises(AiUnavailable) as exc:
        await llm.parse(PROMPT, VALUES, Answer, CallMeta("persona"))
    assert exc.value.reason == "error"
    assert [r.status for r in await rows(factory)] == ["error", "error"]


async def test_the_daily_budget_stops_calls(factory: Any) -> None:
    async with factory() as session, session.begin():
        session.add(
            LlmCall(
                feature="grade",
                model="gpt-6.1-sol",
                prompt_version="grade@1",
                cost_usd=Decimal("5.01"),
                status="ok",
            )
        )
    client = FakeClient()
    llm = adapter(factory, client, llm_daily_budget_usd=5.0)
    with pytest.raises(AiUnavailable) as exc:
        await llm.parse(PROMPT, VALUES, Answer, CallMeta("persona"))
    assert exc.value.reason == "budget"
    assert client.models == []  # refused before any spend


async def test_feature_flags_and_a_missing_key_switch_ai_off(factory: Any) -> None:
    llm = adapter(factory, FakeClient(), ai_personas=False)
    assert not llm.enabled("persona") and not llm.enabled("selfcheck")
    assert llm.enabled("grade")
    with pytest.raises(AiUnavailable) as exc:
        await llm.parse(PROMPT, VALUES, Answer, CallMeta("persona"))
    assert exc.value.reason == "disabled"
    keyless = OpenAiLlm(Settings(_env_file=None), factory)  # type: ignore[call-arg]
    assert not keyless.enabled("grade")


async def test_a_stream_is_metered_once_it_ends(factory: Any) -> None:
    llm = adapter(factory, FakeClient())
    text = "".join([d async for d in llm.stream(PROMPT, VALUES, CallMeta("persona"))])
    assert text == "Hello"
    [row] = await rows(factory)
    assert (row.status, row.output_tokens) == ("ok", 2)


async def test_a_stream_falls_back_only_before_it_has_said_anything(factory: Any) -> None:
    client = FakeClient(failing={"gpt-6-luna"})
    llm = adapter(factory, client)
    assert "".join([d async for d in llm.stream(PROMPT, VALUES, CallMeta("persona"))]) == "Hello"
    assert client.models == ["gpt-6-luna", "gpt-6-sol"]


async def test_traces_carry_the_prompt_version(factory: Any) -> None:
    llm = adapter(factory, FakeClient())
    trace = FakeTrace()
    llm._langfuse = trace  # pyright: ignore[reportPrivateUsage]
    await llm.parse(PROMPT, VALUES, Answer, CallMeta("persona", None, None))
    assert trace.started[0]["version"] == "probe@7"
    assert trace.started[0]["metadata"]["prompt"] == "probe@7"
    assert trace.updates[0]["cost_details"]["total"] > 0
    [row] = await rows(factory)
    assert row.trace_id == "t-1"
