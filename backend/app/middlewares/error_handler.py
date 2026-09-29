"""Global error handling. Every error leaves the API in this shape:

    {"success": false,
     "error": {"code": "NOT_FOUND", "message": "...", "details": ..., "request_id": "..."}}
"""

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.ai.exceptions import AIResponseParseError, AllProvidersFailedError, UnknownProviderError
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.schemas.common import ErrorDetail, ErrorResponse
from app.utils.logger import get_logger

logger = get_logger(__name__)

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
}


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(
            code=code,
            message=message,
            details=details,
            request_id=getattr(request.state, "request_id", None),
        )
    )
    return JSONResponse(status_code=status_code, content=jsonable_encoder(body), headers=headers)


async def _app_exception(request: Request, exc: AppException) -> JSONResponse:
    return error_response(request, exc.status_code, exc.code, exc.message, exc.details)


async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    status = exc.status_code
    code = _STATUS_CODES.get(status, f"HTTP_{status}")
    if isinstance(exc.detail, str):
        message, details = exc.detail, None
    else:
        message, details = HTTPStatus(status).phrase, exc.detail
    return error_response(request, status, code, message, details, headers=getattr(exc, "headers", None))


async def _validation_exception(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {
            "field": ".".join(str(part) for part in err.get("loc", ())),
            "message": err.get("msg"),
            "type": err.get("type"),
        }
        for err in exc.errors()
    ]
    return error_response(request, 422, "VALIDATION_ERROR", "Request validation failed", details)


async def _integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Integrity error: %s", exc.orig)
    return error_response(request, 409, "CONFLICT", "Request conflicts with existing data")


async def _all_providers_failed(request: Request, exc: AllProvidersFailedError) -> JSONResponse:
    details = [a.model_dump() for a in exc.attempts]
    return error_response(request, 502, "AI_PROVIDERS_FAILED", str(exc), details)


async def _unknown_provider(request: Request, exc: UnknownProviderError) -> JSONResponse:
    return error_response(request, 400, "AI_UNKNOWN_PROVIDER", str(exc))


async def _ai_parse_error(request: Request, exc: AIResponseParseError) -> JSONResponse:
    return error_response(request, 502, "AI_BAD_RESPONSE", str(exc))


def unhandled_exception_response(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    details = {"exception": type(exc).__name__, "detail": str(exc)} if get_settings().DEBUG else None
    return error_response(request, 500, "INTERNAL_ERROR", "Internal server error", details)


class CatchAllErrorMiddleware(BaseHTTPMiddleware):
    """Turns uncaught exceptions into the standard error shape. It sits inside the
    CORS and logging middlewares, so 500s still carry CORS headers and get logged."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            return unhandled_exception_response(request, exc)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, _app_exception)
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_exception)
    app.add_exception_handler(IntegrityError, _integrity_error)
    app.add_exception_handler(AllProvidersFailedError, _all_providers_failed)
    app.add_exception_handler(UnknownProviderError, _unknown_provider)
    app.add_exception_handler(AIResponseParseError, _ai_parse_error)
