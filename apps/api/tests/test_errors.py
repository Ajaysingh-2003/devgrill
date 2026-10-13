from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from devgrill.config import Settings
from devgrill_api.errors import PROBLEM_CONTENT_TYPE, AppError
from devgrill_api.main import create_app


class Echo(BaseModel):
    count: int


def _app_with_test_routes(settings: Settings) -> FastAPI:
    app = create_app(settings)

    @app.post("/_test/echo")
    async def echo(body: Echo) -> Echo:
        return body

    @app.get("/_test/conflict")
    async def conflict() -> None:
        raise AppError(409, "active_attempt_exists", "You already have a live incident.")

    @app.get("/_test/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal detail")

    return app


def test_not_found_is_problem_json(client: TestClient) -> None:
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith(PROBLEM_CONTENT_TYPE)
    assert response.json()["code"] == "not_found"


def test_validation_error_lists_fields(settings: Settings) -> None:
    with TestClient(_app_with_test_routes(settings)) as client:
        response = client.post("/_test/echo", json={"count": "many"})
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["errors"][0]["loc"] == ["body", "count"]


def test_app_error_maps_status_and_code(settings: Settings) -> None:
    with TestClient(_app_with_test_routes(settings)) as client:
        response = client.get("/_test/conflict")
    assert response.status_code == 409
    body = response.json()
    assert body["type"].endswith("/active_attempt_exists")
    assert body["detail"] == "You already have a live incident."


def test_unhandled_error_hides_internals(settings: Settings) -> None:
    with TestClient(_app_with_test_routes(settings), raise_server_exceptions=False) as client:
        response = client.get("/_test/crash")
    assert response.status_code == 500
    assert "secret" not in response.text
    assert response.json()["code"] == "internal_error"


def test_request_id_is_echoed_or_generated(client: TestClient) -> None:
    echoed = client.get("/healthz", headers={"x-request-id": "req-123"})
    assert echoed.headers["x-request-id"] == "req-123"
    generated = client.get("/healthz", headers={"x-request-id": "bad id with spaces"})
    assert generated.headers["x-request-id"] != "bad id with spaces"
    assert len(generated.headers["x-request-id"]) == 32
