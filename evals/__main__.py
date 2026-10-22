"""`uv run python -m evals [suite ...] [--limit N]`: run the AI evals against the real models.

Needs OPENAI_API_KEY. Writes evals/reports/<suite>.json and a summary (also to the GitHub
job summary in CI). Exits 1 when a gate fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from decimal import Decimal

from devgrill.config import get_settings
from evals.harness import REPORTS, EvalLlm
from evals.suites import SUITES, Result

#: Evals stop spending past this (they run outside the platform's daily budget).
EVAL_BUDGET_USD = float(os.environ.get("EVAL_BUDGET_USD", "3"))


def summary(results: list[Result], spent: Decimal) -> str:
    lines = ["| Suite | Gate | Metrics |", "|---|---|---|"]
    for r in results:
        metrics = ", ".join(f"{k}={v}" for k, v in r.metrics.items() if k != "by_feature")
        lines.append(f"| {r.suite} | {'pass' if r.passed else 'FAIL'} | {metrics} |")
    lines.append(f"\nSpent ${spent.quantize(Decimal('0.0001'))} on this run.")
    for r in results:
        if r.failures:
            lines.append(f"\n**{r.suite}** failures:")
            lines += [f"- {f[:300]}" for f in r.failures[:20]]
    return "\n".join(lines)


async def main(names: list[str], limit: int | None) -> int:
    settings = get_settings().model_copy(update={"llm_daily_budget_usd": EVAL_BUDGET_USD})
    if not settings.openai_api_key.get_secret_value():
        print("OPENAI_API_KEY is not set: the evals need the real models.", file=sys.stderr)
        return 2
    llm = EvalLlm(settings)
    results: list[Result] = []
    try:
        for name in names:
            print(f"running {name}...", flush=True)
            result = await SUITES[name](llm, limit)
            results.append(result)
            REPORTS.mkdir(exist_ok=True)
            (REPORTS / f"{name}.json").write_text(
                json.dumps(asdict(result), indent=2, default=str), encoding="utf-8"
            )
    finally:
        await llm.close()
    text = summary(results, llm.cost())
    print(text)
    if path := os.environ.get("GITHUB_STEP_SUMMARY"):
        await asyncio.to_thread(_append, path, text + "\n")
    return 0 if all(r.passed for r in results) else 1


def _append(path: str, text: str) -> None:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="evals")
    parser.add_argument("suites", nargs="*", help=f"any of {', '.join(SUITES)} (default: all)")
    parser.add_argument("--limit", type=int, default=None, help="items per suite (smoke runs)")
    args = parser.parse_args()
    unknown = [s for s in args.suites if s not in SUITES]
    if unknown:
        parser.error(f"unknown suite(s): {', '.join(unknown)}")
    sys.exit(asyncio.run(main(args.suites or list(SUITES), args.limit)))
