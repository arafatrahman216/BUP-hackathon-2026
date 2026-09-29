from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.dependencies import DbSession, Simulator, State

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: DbSession, sim: Simulator, state: State) -> dict:
    settings = get_settings()
    try:
        await session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    return {
        "status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV, "database": database,
        "simulator": {
            "connected": state.sim_connected, "link": state.link, "circuit": sim.breaker.state,
            "last_latency_ms": sim.last_latency_ms, "last_error": sim.last_error,
        },
        "pipeline": {
            "enabled": settings.PIPELINE_ENABLED, "runs": state.runs, "acting": state.acting,
            "last_processed_tick": state.last_processed_tick, "dashboard_subscribers": state.subscriber_count,
            "stages": {s.name: s.status for s in state.stages},
        },
    }
