"""The LLM port on the OpenAI Responses API (ADR 016).

Every call:
1. is refused up front (`AiUnavailable`) when the feature is off, there is no key, or today's
   spend (IST day, every feature) has reached `LLM_DAILY_BUDGET_USD`;
2. runs on the prompt's model (fast or judge) with the SDK's retries (backoff with jitter)
   and a timeout; if it still fails, once more on the fallback model;
3. is metered in `llm_calls` (tokens, cost, latency, prompt version, status), successful or
   not, and traced to Langfuse when it's configured (inputs redacted).

Per-user allowances (teammate messages, reviews) are checked by the features, which know the
plan; this layer enforces the money.
"""

from __future__ import annotations

import ssl
import time
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from datetime import time as dtime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import openai
import structlog
import truststore
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from devgrill.ai.port import AiUnavailable, CallMeta, Feature
from devgrill.ai.pricing import cost_usd
from devgrill.ai.registry import Prompt
from devgrill.ai.safety import redact
from devgrill.config import Settings
from devgrill.domain.streaks import DEFAULT_TIMEZONE
from devgrill.infra.models import LlmCall

log = structlog.get_logger(__name__)

_FLAGS: dict[Feature, str] = {
    "persona": "ai_personas",
    "nudge": "ai_nudges",
    "selfcheck": "ai_personas",
    "grade": "ai_grading",
    "classify": "ai_classify",
    "embed": "ai_classify",
    "coach": "ai_coach",
}
#: Warn (once per day and process) when spend passes this share of the budget.
ALARM_AT = Decimal("0.8")


def day_start(now: datetime, timezone: str = DEFAULT_TIMEZONE) -> datetime:
    local = now.astimezone(ZoneInfo(timezone)).date()
    return datetime.combine(local, dtime.min, tzinfo=ZoneInfo(timezone)).astimezone(UTC)


class OpenAiLlm:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        key = settings.openai_api_key.get_secret_value()
        # The OS trust store: corporate proxies re-sign TLS with a root certifi doesn't hold.
        tls = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.client = client or (
            openai.AsyncOpenAI(
                api_key=key,
                timeout=settings.llm_timeout_s,
                max_retries=2,
                http_client=openai.DefaultAsyncHttpxClient(verify=tls),
            )
            if key
            else None
        )
        self._alarmed_on: str | None = None
        self._langfuse: Any = None
        if settings.langfuse_host and settings.langfuse_public_key:
            from langfuse import Langfuse

            self._langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key.get_secret_value(),
                host=settings.langfuse_host,
                environment=settings.env,
                mask=lambda *, data, **_: redact(data) if isinstance(data, str) else data,
            )

    # ------------------------------------------------------------------------ gates

    def enabled(self, feature: Feature) -> bool:
        return self.client is not None and bool(getattr(self.settings, _FLAGS[feature]))

    async def spent_today(self, now: datetime | None = None) -> Decimal:
        async with self.session_factory() as session:
            total = await session.scalar(
                select(func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(
                    LlmCall.created_at >= day_start(now or datetime.now(UTC))
                )
            )
        return Decimal(total or 0)

    async def _gate(self, meta: CallMeta) -> None:
        if not self.enabled(meta.feature):
            raise AiUnavailable("disabled", meta.feature)
        budget = Decimal(str(self.settings.llm_daily_budget_usd))
        spent = await self.spent_today()
        if spent >= budget:
            log.warning("llm.budget_exhausted", spent=str(spent), budget=str(budget))
            raise AiUnavailable("budget", f"today's AI budget (${budget}) is spent")
        today = datetime.now(UTC).date().isoformat()
        if spent >= budget * ALARM_AT and self._alarmed_on != today:
            self._alarmed_on = today
            log.warning("llm.budget_alarm", spent=str(spent), budget=str(budget))

    # ---------------------------------------------------------------------- metering

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
        input_tokens = int(
            getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
        )
        details = getattr(usage, "input_tokens_details", None)
        cached = int(getattr(details, "cached_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        row = LlmCall(
            id=meta.call_id if status == "ok" else uuid.uuid4(),
            feature=meta.feature,
            model=model,
            prompt_version=prompt_id,
            input_tokens=input_tokens,
            cached_tokens=cached,
            output_tokens=output_tokens,
            cost_usd=cost_usd(
                model, input_tokens=input_tokens, cached_tokens=cached, output_tokens=output_tokens
            ),
            latency_ms=round((time.perf_counter() - started) * 1000),
            attempt_id=meta.attempt_id,
            user_id=meta.user_id,
            trace_id=trace_id,
            status=status,
        )
        try:
            async with self.session_factory() as session, session.begin():
                session.add(row)
        except Exception as exc:  # metering must not take the feature down
            log.error("llm.meter_failed", error=str(exc)[:200])

    def _trace(
        self, prompt: Prompt, model: str, meta: CallMeta, instructions: str, user: str
    ) -> Any:
        if self._langfuse is None:
            return None
        try:
            return self._langfuse.start_observation(
                name=f"{meta.feature}:{prompt.name}",
                as_type="generation",
                model=model,
                version=prompt.id,
                input=[
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": user},
                ],
                metadata={
                    "attempt_id": str(meta.attempt_id) if meta.attempt_id else None,
                    "user_id": str(meta.user_id) if meta.user_id else None,
                    "prompt": prompt.id,
                },
            )
        except Exception as exc:
            log.warning("llm.trace_failed", error=str(exc)[:200])
            return None

    @staticmethod
    def _end_trace(
        obs: Any, output: Any, usage: Any, cost: Decimal | None, error: str | None
    ) -> None:
        if obs is None:
            return
        try:
            update: dict[str, Any] = {"output": output}
            if usage is not None:
                update["usage_details"] = {
                    "input": int(getattr(usage, "input_tokens", 0) or 0),
                    "output": int(getattr(usage, "output_tokens", 0) or 0),
                }
            if cost is not None:
                update["cost_details"] = {"total": float(cost)}
            if error:
                update["level"] = "ERROR"
                update["status_message"] = error[:500]
            obs.update(**update)
            obs.end()
        except Exception as exc:
            log.warning("llm.trace_failed", error=str(exc)[:200])

    # ------------------------------------------------------------------------- calls

    def _models(self, prompt: Prompt) -> list[str]:
        primary = (
            self.settings.llm_model_judge
            if prompt.model == "judge"
            else self.settings.llm_model_fast
        )
        fallback = self.settings.llm_model_fallback
        return [primary] if fallback == primary else [primary, fallback]

    def _kwargs(self, prompt: Prompt, model: str, instructions: str, user: str) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": user,
            "max_output_tokens": prompt.max_output,
            "store": False,  # nothing kept on OpenAI's side beyond abuse monitoring
        }
        if prompt.reasoning:
            kwargs["reasoning"] = {"effort": prompt.reasoning}
        return kwargs

    async def parse[T: BaseModel](
        self, prompt: Prompt, values: Mapping[str, str], schema: type[T], meta: CallMeta
    ) -> T:
        await self._gate(meta)
        assert self.client is not None
        instructions, user = prompt.render(**values)
        last: Exception | None = None
        for model in self._models(prompt):
            started = time.perf_counter()
            obs = self._trace(prompt, model, meta, instructions, user)
            trace_id = getattr(obs, "trace_id", None)
            try:
                response = await self.client.responses.parse(
                    text_format=schema, **self._kwargs(prompt, model, instructions, user)
                )
            except openai.OpenAIError as exc:
                last = exc
                await self._meter(meta, prompt.id, model, None, started, "error", trace_id)
                self._end_trace(obs, None, None, None, str(exc))
                log.warning(
                    "llm.call_failed", feature=meta.feature, model=model, error=str(exc)[:300]
                )
                continue
            parsed = response.output_parsed
            status = "ok" if parsed is not None else "refused"
            await self._meter(meta, prompt.id, model, response.usage, started, status, trace_id)
            usage = response.usage
            self._end_trace(
                obs,
                parsed.model_dump() if parsed is not None else None,
                usage,
                cost_usd(
                    model,
                    input_tokens=usage.input_tokens if usage else 0,
                    cached_tokens=usage.input_tokens_details.cached_tokens if usage else 0,
                    output_tokens=usage.output_tokens if usage else 0,
                ),
                None if parsed is not None else "no parsed output",
            )
            if parsed is None:
                last = AiUnavailable("error", "the model returned no structured output")
                continue
            return parsed
        raise AiUnavailable("error", str(last)[:300] if last else "no model answered")

    async def stream(
        self, prompt: Prompt, values: Mapping[str, str], meta: CallMeta
    ) -> AsyncIterator[str]:
        await self._gate(meta)
        assert self.client is not None
        instructions, user = prompt.render(**values)
        last: Exception | None = None
        for model in self._models(prompt):
            started = time.perf_counter()
            obs = self._trace(prompt, model, meta, instructions, user)
            trace_id = getattr(obs, "trace_id", None)
            text, sent = "", False
            try:
                async with self.client.responses.stream(
                    **self._kwargs(prompt, model, instructions, user)
                ) as events:
                    async for event in events:
                        if event.type == "response.output_text.delta":
                            text += event.delta
                            sent = True
                            yield event.delta
                    final = await events.get_final_response()
            except openai.OpenAIError as exc:
                last = exc
                await self._meter(meta, prompt.id, model, None, started, "error", trace_id)
                self._end_trace(obs, text or None, None, None, str(exc))
                log.warning(
                    "llm.stream_failed", feature=meta.feature, model=model, error=str(exc)[:300]
                )
                if sent:  # half a reply already shown: don't splice another model's onto it
                    raise AiUnavailable("error", str(exc)[:300]) from exc
                continue
            usage = final.usage
            await self._meter(meta, prompt.id, model, usage, started, "ok", trace_id)
            self._end_trace(
                obs,
                text,
                usage,
                cost_usd(
                    model,
                    input_tokens=usage.input_tokens if usage else 0,
                    cached_tokens=usage.input_tokens_details.cached_tokens if usage else 0,
                    output_tokens=usage.output_tokens if usage else 0,
                ),
                None,
            )
            return
        raise AiUnavailable("error", str(last)[:300] if last else "no model answered")

    async def embed(self, texts: list[str], meta: CallMeta) -> list[list[float]]:
        await self._gate(meta)
        assert self.client is not None
        model = self.settings.llm_model_embedding
        started = time.perf_counter()
        try:
            response = await self.client.embeddings.create(
                model=model, input=[redact(t)[:8000] for t in texts]
            )
        except openai.OpenAIError as exc:
            await self._meter(meta, "embedding@1", model, None, started, "error", None)
            raise AiUnavailable("error", str(exc)[:300]) from exc
        await self._meter(meta, "embedding@1", model, response.usage, started, "ok", None)
        return [d.embedding for d in response.data]

    async def close(self) -> None:
        if self.client is not None:
            await self.client.close()
        if self._langfuse is not None:
            try:
                self._langfuse.flush()
            except Exception as exc:
                log.warning("llm.trace_flush_failed", error=str(exc)[:200])
