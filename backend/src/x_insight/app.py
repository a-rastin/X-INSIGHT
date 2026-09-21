from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from x_insight import db
from x_insight.assessments.content import router as assessments_content_router
from x_insight.cases.encounters import router as encounters_router
from x_insight.cases.history_content import router as history_content_router
from x_insight.cases.notes import router as notes_router
from x_insight.cases.patients import router as patients_router
from x_insight.contracts import MAX_BODY_BYTES, error_body, new_request_id
from x_insight.identity.accounts import router as accounts_router
from x_insight.identity.routes import router as identity_router

app = FastAPI()

_HTTP_CODE_MAP = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    412: "STALE_REVISION",
    422: "INVALID_CONTENT",
    429: "RATE_LIMITED",
}


def _request_id(request: Request) -> str:
    scope_id: object = request.scope.get("request_id")
    if isinstance(scope_id, str) and scope_id:
        return scope_id
    header_id: str | None = request.headers.get("x-request-id")
    if header_id:
        return header_id
    return new_request_id()


class RequestContextMiddleware:
    """Propagate/generate request IDs, enforce body size, echo ID on errors."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        raw_headers = scope.get("headers", [])
        headers = {k.decode().lower(): v.decode() for k, v in raw_headers}
        request_id = headers.get("x-request-id") or new_request_id()
        scope["request_id"] = request_id

        content_length = headers.get("content-length", "")
        if content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
            body = json.dumps(
                error_body(
                    "PAYLOAD_TOO_LARGE",
                    f"Request body exceeds {MAX_BODY_BYTES} bytes.",
                    request_id,
                )
            ).encode("utf-8")
            response_headers = [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"x-request-id", request_id.encode()),
            ]
            await send(
                {
                    "type": "http.response.start",
                    "status": 413,
                    "headers": response_headers,
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_id(message: Any) -> None:
            if message.get("type") == "http.response.start":
                existing = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k != b"x-request-id"
                ]
                existing.append((b"x-request-id", request_id.encode()))
                message["headers"] = existing
            await send(message)

        await self.app(scope, receive, send_with_id)


app.add_middleware(RequestContextMiddleware)


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return await validation_exception_handler(request, exc)


@app.exception_handler(Exception)
async def _unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    return await unhandled_exception_handler(request, exc)


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Standard envelope for HTTP errors (shared with handler registration)."""
    request_id = _request_id(request)
    code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
    message = str(exc.detail) if isinstance(exc.detail, str) else code
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message, request_id),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Standard 422 envelope with field errors."""
    request_id = _request_id(request)
    field_errors: dict[str, str] = {}
    for error in exc.errors():
        loc = ".".join(str(part) for part in error.get("loc", ()))
        field_errors[loc or "body"] = str(error.get("msg", "invalid"))
    return JSONResponse(
        status_code=422,
        content=error_body(
            "INVALID_CONTENT",
            "Request content failed validation.",
            request_id,
            field_errors=field_errors,
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Safe 500 envelope: no traceback, no secrets."""
    del exc
    request_id = _request_id(request)
    return JSONResponse(
        status_code=500,
        content=error_body("INTERNAL_ERROR", "Internal error.", request_id),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the standard contract handlers to another app (tests reuse)."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)


app.include_router(identity_router, prefix="/api/v1")
app.include_router(accounts_router, prefix="/api/v1")
app.include_router(patients_router, prefix="/api/v1")
app.include_router(notes_router, prefix="/api/v1")
app.include_router(encounters_router, prefix="/api/v1")
app.include_router(history_content_router, prefix="/api/v1")
app.include_router(assessments_content_router, prefix="/api/v1")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Liveness only; never touches the database."""
    return {"status": "ok"}


@app.get("/api/v1/ready")
def ready(request: Request) -> Any:
    """Readiness: database reachable and schema at the expected revision."""
    request_id = _request_id(request)
    try:
        db.check_readiness()
    except db.ReadinessError as exc:
        if exc.code == "UNAVAILABLE":
            return JSONResponse(
                status_code=503,
                content=error_body(
                    "UNAVAILABLE",
                    "Database is unavailable. Retry later.",
                    request_id,
                    retryable=True,
                ),
            )
        return JSONResponse(
            status_code=503,
            content=error_body(
                "INCOMPATIBLE_SCHEMA",
                "Database schema is not compatible. Run migrations.",
                request_id,
            ),
        )
    return {"status": "ready"}
