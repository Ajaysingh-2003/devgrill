"""What a model call costs (ADR 016). Re-check at implementation and on every model change.

List prices per million tokens: input, cached input, output. Sources: the plan (PLAN §13.1)
and the model launch notes for the GPT-6 tier (OpenAI's pricing page wasn't reachable from the
build machine on 2026-10-22); the owner confirms them against OpenAI's page. Reasoning tokens
are billed as output. A model missing here is metered at the most expensive known price, so an
unknown model can only over-count the budget, never under-count it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final


@dataclass(frozen=True, slots=True)
class Price:
    input: Decimal
    cached: Decimal
    output: Decimal


PRICES: Final[dict[str, Price]] = {
    "gpt-6-luna": Price(Decimal("0.10"), Decimal("0.01"), Decimal("0.50")),
    "gpt-6-sol": Price(Decimal("2.00"), Decimal("0.20"), Decimal("10.00")),
    "gpt-6.1-sol": Price(Decimal("2.00"), Decimal("0.20"), Decimal("10.00")),
    "gpt-6-astra": Price(Decimal("10.00"), Decimal("1.00"), Decimal("50.00")),
    "text-embedding-3-small": Price(Decimal("0.02"), Decimal("0.02"), Decimal("0")),
}
_MOST_EXPENSIVE: Final = max(PRICES.values(), key=lambda p: p.output)
_PER: Final = Decimal(1_000_000)


def cost_usd(model: str, *, input_tokens: int, cached_tokens: int, output_tokens: int) -> Decimal:
    price = PRICES.get(model, _MOST_EXPENSIVE)
    fresh = max(0, input_tokens - cached_tokens)
    total = (
        fresh * price.input + cached_tokens * price.cached + output_tokens * price.output
    ) / _PER
    return total.quantize(Decimal("0.000001"))
