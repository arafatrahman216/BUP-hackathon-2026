"""Simple in-memory sliding-window rate limiter for selected path prefixes.

Only non-GET requests count (GET/HEAD/OPTIONS are metadata reads like /ai/providers,
not model calls).

Good enough for a single process. With several workers/instances each keeps its own
counters; switch to Redis if you need a shared limit.
"""

import math
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.middlewares.error_handler import error_response


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, max_requests: int, window_seconds: int, path_prefixes: list[str]) -> None:
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.path_prefixes = path_prefixes
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _matching_prefix(self, path: str) -> str | None:
        return next((p for p in self.path_prefixes if path.startswith(p)), None)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        prefix = self._matching_prefix(request.url.path)
        if prefix is None or request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        hits = self._hits[f"{client}:{prefix}"]
        now = time.monotonic()
        while hits and hits[0] <= now - self.window_seconds:
            hits.popleft()

        if len(hits) >= self.max_requests:
            retry_after = max(1, math.ceil(hits[0] + self.window_seconds - now))
            return error_response(
                request,
                429,
                "RATE_LIMITED",
                f"Too many requests. Try again in {retry_after}s.",
                {"limit": self.max_requests, "window_seconds": self.window_seconds},
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(self.max_requests - len(hits))
        return response
