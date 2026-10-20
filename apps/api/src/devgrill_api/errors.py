"""RFC 9457 problem+json responses for every error the API returns."""

from __future__ import annotations

import re
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://devgrill.dev/problems/"

log = structlog.get_logger(__name__)


class FieldError(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    code: str | None = None
    errors: list[FieldError] | None = None


def _problem(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {PROBLEM_CONTENT_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
    }


#: Error responses every /v1 operation can return, documented so clients (and Schemathesis)
#: know their shape. Each is RFC 9457 problem+json with a machine-readable `code`.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: _problem("Bad request (e.g. an invalid cursor)."),
    401: _problem("Missing or invalid credentials."),
    403: _problem("Signed in, but not allowed."),
    404: _problem("Not found."),
    409: _problem("Conflict (e.g. a request with this Idempotency-Key is still running)."),
    422: _problem("The request is invalid; see `errors`."),
    429: _problem("Rate limited; see Retry-After."),
    500: _problem("Server error."),
    503: _problem("Temporarily unavailable."),
}


def problem_response(
    status: int,
    *,
    code: str | None = None,
    detail: str | None = None,
    instance: str | None = None,
    errors: list[FieldError] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    problem = Problem(
        type=f"{PROBLEM_TYPE_BASE}{code}" if code else "about:blank",
        title=HTTPStatus(status).phrase,
        status=status,
        detail=detail,
        instance=instance,
        code=code,
        errors=errors,
    )
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=status,
        media_type=PROBLEM_CONTENT_TYPE,
        headers=headers,
    )


class AppError(Exception):
    """Raise from routes/services for an expected, client-facing error."""

    def __init__(
        self,
        status: int,
        code: str,
        detail: str | None = None,
        *,
        headers: dict[str, str] | None = None,
        instance: str | None = None,
    ) -> None:
        super().__init__(detail or code)
        self.status = status
        self.code = code
        self.detail = detail
        self.headers = headers
        #: Overrides the problem's `instance` (default: the request path), e.g. to point a 409
        #: at the resource it conflicts with.
        self.instance = instance


def _allowed_methods(request: Request) -> str:
    patterns: list[tuple[re.Pattern[str], str]] | None = getattr(
        request.app.state, "allow_patterns", None
    )
    if patterns is None:
        patterns = []
        for template, operations in request.app.openapi().get("paths", {}).items():
            regex = "[^/]+".join(re.escape(part) for part in re.split(r"\{[^/]+?\}", template))
            methods = ", ".join(sorted(m.upper() for m in operations))
            patterns.append((re.compile(f"^{regex}$"), methods))
        request.app.state.allow_patterns = patterns
    for pattern, methods in patterns:
        if pattern.match(request.url.path):
            return methods
    return ""


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return problem_response(
            exc.status,
            code=exc.code,
            detail=exc.detail,
            instance=exc.instance or request.url.path,
            headers=exc.headers,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = HTTPStatus(exc.status_code).name.lower()
        detail = exc.detail if isinstance(exc.detail, str) else None
        headers: Any = getattr(exc, "headers", None)
        if exc.status_code == 405:
            # Starlette lists only the first matching route's methods (GET /me and PATCH /me
            # are separate routes); the OpenAPI paths know every method for the path.
            headers = {**(headers or {}), "Allow": _allowed_methods(request)}
        return problem_response(
            exc.status_code, code=code, detail=detail, instance=request.url.path, headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            FieldError(
                loc=list(err.get("loc", ())), msg=str(err.get("msg")), type=str(err.get("type"))
            )
            for err in exc.errors()
        ]
        return problem_response(
            422,
            code="validation_error",
            detail="The request is invalid.",
            instance=request.url.path,
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", path=request.url.path)
        return problem_response(
            500,
            code="internal_error",
            detail="Something went wrong on our side.",
            instance=request.url.path,
        )
