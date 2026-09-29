from fastapi import FastAPI

from app.core.config import Settings
from app.middlewares.cors import setup_cors
from app.middlewares.metrics import MetricsMiddleware
from app.middlewares.error_handler import CatchAllErrorMiddleware, register_exception_handlers
from app.middlewares.rate_limiter import RateLimitMiddleware
from app.middlewares.request_logging import RequestLoggingMiddleware


def setup_middlewares(app: FastAPI, settings: Settings) -> None:
    """The last middleware added is the outermost. Request flow:
    CORS -> Metrics -> RequestLogging -> CatchAllError -> RateLimit -> route."""
    if settings.RATE_LIMIT_ENABLED:
        app.add_middleware(
            RateLimitMiddleware,
            max_requests=settings.RATE_LIMIT_REQUESTS,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
            path_prefixes=settings.rate_limit_path_prefixes,
        )
    app.add_middleware(CatchAllErrorMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(MetricsMiddleware)
    setup_cors(app, settings)
    register_exception_handlers(app)


__all__ = ["setup_middlewares"]
