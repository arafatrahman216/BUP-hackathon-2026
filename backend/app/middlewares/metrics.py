import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.utils.metrics import HTTP_LATENCY, HTTP_REQUESTS, request_window

# long-lived or self-referential: they would skew latency
SKIP_SUFFIXES = ("/metrics", "/stream")


class MetricsMiddleware(BaseHTTPMiddleware):
    """Counts requests and latency per route template (`/recommendations/{rec_id}`, not ids).
    5xx responses count as errors."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.endswith(SKIP_SUFFIXES):
            return await call_next(request)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            seconds = time.perf_counter() - started
            route = getattr(request.scope.get("route"), "path", None) or "unmatched"
            HTTP_REQUESTS.labels(request.method, route, str(status)).inc()
            HTTP_LATENCY.labels(route).observe(seconds)
            request_window.add(seconds, status >= 500)
