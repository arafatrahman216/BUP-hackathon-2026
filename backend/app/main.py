from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.ai import close_llm_client, get_llm_client
from app.controllers import api_router
from app.core.config import get_settings
from app.core.database import engine, init_db
from app.middlewares import setup_middlewares
from app.repositories.storage_repository import close_storage_repository
from app.schemas.common import ErrorResponse
from app.utils.logger import get_logger, setup_logging

settings = get_settings()
setup_logging(settings.LOG_LEVEL)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    llm = get_llm_client()  # fail fast on a bad AI_PROVIDER_ORDER
    logger.info("AI chain: %s (fallback %s)", llm.describe()["active_chain"],
                "on" if llm.fallback_enabled else "off")
    logger.info("%s started in %s mode", settings.APP_NAME, settings.APP_ENV)
    yield
    await close_llm_client()
    await close_storage_repository()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        lifespan=lifespan,
        responses={
            400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
            422: {"model": ErrorResponse}, 500: {"model": ErrorResponse},
        },
    )
    setup_middlewares(app, settings)
    app.include_router(api_router, prefix=settings.API_PREFIX)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"name": settings.APP_NAME, "docs": "/docs", "api": settings.API_PREFIX}

    return app


app = create_app()
