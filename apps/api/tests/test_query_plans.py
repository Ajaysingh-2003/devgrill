"""Library queries stay fast at catalog scale (phase 2 gate: index use, < 20 ms on 10k scenarios).

The plans are taken from the exact statements the API runs (devgrill.infra.repositories).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import Executable

from devgrill.domain.enums import Difficulty
from devgrill.infra.repositories.catalog import scenarios_query
from devgrill_content.seed import seed

pytestmark = pytest.mark.integration

CONTENT = Path(__file__).resolve().parents[3] / "content"
SCENARIOS = 10_000
BUDGET_MS = 20.0

BULK_INSERT = text(
    """
    INSERT INTO app.scenarios (slug, track_id, topic_id, title, summary, difficulty, est_minutes,
                               status, tags)
    SELECT 'bulk-' || g,
           t.id,
           (SELECT id FROM app.topics WHERE track_id = t.id ORDER BY position LIMIT 1),
           'Bulk scenario ' || g,
           'Synthetic scenario for query-plan tests',
           (ARRAY['sev4','sev3','sev2','sev1'])[1 + g % 4]::app.difficulty,
           10 + g % 30,
           (CASE WHEN g % 10 = 0 THEN 'draft' ELSE 'published' END)::app.scenario_status,
           ARRAY['bulk']
    FROM generate_series(1, :n) AS g
    JOIN LATERAL (
        SELECT id FROM app.tracks WHERE status = 'published'
        ORDER BY position OFFSET g % 6 LIMIT 1
    ) t ON true
    """
)


def _sql(stmt: Executable) -> str:
    compiled = stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})  # type: ignore[attr-defined]
    return str(compiled)


async def _explain(session: AsyncSession, sql: str) -> dict[str, Any]:
    result = await session.execute(text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}"))
    plan: dict[str, Any] = result.scalar_one()[0]
    return plan


def _nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    out = [node]
    for child in node.get("Plans", []):
        out += _nodes(child)
    return out


@pytest.fixture
async def big_catalog(db_session: AsyncSession) -> AsyncSession:
    await seed(db_session, CONTENT)
    await db_session.execute(BULK_INSERT, {"n": SCENARIOS})
    await db_session.commit()
    await db_session.execute(text("ANALYZE app.scenarios"))
    await db_session.execute(text("ANALYZE app.tracks"))
    await db_session.execute(text("ANALYZE app.topics"))
    return db_session


QUERIES = {
    "first page": scenarios_query(limit=21),
    "later page": scenarios_query(after_slug="bulk-5000", limit=21),
    "track filter": scenarios_query(track_slug="caching", limit=21),
    "track + difficulty": scenarios_query(
        track_slug="caching", difficulty=Difficulty.SEV1, limit=21
    ),
    "search": scenarios_query(query="Bulk scenario 99", limit=21),
}


@pytest.mark.parametrize("name", list(QUERIES))
async def test_library_queries_are_fast(big_catalog: AsyncSession, name: str) -> None:
    plan = await _explain(big_catalog, _sql(QUERIES[name]))
    # Warm run, as the API would see it: the first execution pays for cold buffers.
    plan = await _explain(big_catalog, _sql(QUERIES[name]))
    assert plan["Execution Time"] < BUDGET_MS, f"{name}: {plan['Execution Time']:.1f} ms"


@pytest.mark.parametrize("name", ["first page", "later page", "track filter"])
async def test_paginated_queries_use_an_index_on_scenarios(
    big_catalog: AsyncSession, name: str
) -> None:
    plan = await _explain(big_catalog, _sql(QUERIES[name]))
    scans = [n for n in _nodes(plan["Plan"]) if n.get("Relation Name") == "scenarios"]
    assert scans, "scenarios not scanned?"
    assert all(n["Node Type"] != "Seq Scan" for n in scans), [n["Node Type"] for n in scans]


async def test_track_listing_is_fast(big_catalog: AsyncSession) -> None:
    sql = _sql(scenarios_query(track_slug="caching", order_by_difficulty=True))
    await _explain(big_catalog, sql)
    plan = await _explain(big_catalog, sql)
    assert plan["Execution Time"] < BUDGET_MS
