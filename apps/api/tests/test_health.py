import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from devgrill_api import health


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def _ok(_: Request) -> None:
    return None


async def _boom(_: Request) -> None:
    raise ConnectionRefusedError


def test_readyz_ok_when_all_checks_pass(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "READINESS_CHECKS", {"database": _ok, "valkey": _ok})
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["ok"] is True


def test_readyz_degraded_reports_failing_dependency(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health, "READINESS_CHECKS", {"database": _ok, "temporal": _boom})
    response = client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["temporal"] == {
        "ok": False,
        "latency_ms": body["checks"]["temporal"]["latency_ms"],
        "error": "ConnectionRefusedError",
    }


def test_readyz_times_out_slow_dependency(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    async def _slow(_: Request) -> None:
        await asyncio.sleep(5)

    monkeypatch.setattr(health, "READINESS_CHECKS", {"valkey": _slow})
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["valkey"]["error"] == "TimeoutError"


@pytest.mark.integration
def test_readyz_against_local_platform(client: TestClient) -> None:
    """Needs `just deps-up`: real Postgres, Valkey and Temporal."""
    response = client.get("/readyz")
    assert response.status_code == 200, response.json()
