"""Structured application errors and FastAPI exception handlers.

Every error response has the shape::

    {"error": {"code": "...", "message": "...", "details": ..., "request_id": "..."}}

Unhandled exceptions are logged with a traceback server-side but the client only receives a
generic message — no stack traces or internal details leak to users.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("stockwise.errors")


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(self, message: str, *, details: Any = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class ValidationFailedError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    code = "validation_failed"


class PayloadTooLargeError(AppError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    code = "payload_too_large"


class UnsupportedMediaError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_media_type"


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def error_body(request: Request, code: str, message: str, details: Any = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": jsonable_encoder(details),
            "request_id": _request_id(request),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        logger.info("app_error code=%s status=%s msg=%s", exc.code, exc.status_code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(request, exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        issues = [
            {
                "field": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
                "message": err.get("msg"),
                "type": err.get("type"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_body(request, "invalid_request", "Request validation failed.", issues),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else "http_error"
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error."
        return JSONResponse(
            status_code=exc.status_code, content=error_body(request, code, message)
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("unhandled_error path=%s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body(
                request,
                "internal_error",
                "An unexpected server error occurred. The error has been logged.",
            ),
        )
