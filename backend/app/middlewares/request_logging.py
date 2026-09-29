import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.utils.logger import get_logger, request_id_ctx

logger = get_logger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assigns a request id (or reuses the client's X-Request-ID), logs method, path,
    status and duration, and echoes the id back in the X-Request-ID header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
            duration = (time.perf_counter() - started) * 1000
            client = request.client.host if request.client else "-"
            logger.info(
                "%s %s -> %s (%.1fms) client=%s",
                request.method, request.url.path, response.status_code, duration, client,
            )
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx.reset(token)
