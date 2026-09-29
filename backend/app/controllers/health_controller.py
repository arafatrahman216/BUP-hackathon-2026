from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.dependencies import DbSession

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: DbSession) -> dict:
    settings = get_settings()
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV, "database": database}
