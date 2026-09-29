"""System status: health of each component plus p95 latency and error rate.
The same numbers feed the Prometheus gauges scraped at /metrics (Grafana dashboard)."""

import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline.state import PipelineState
from app.repositories.simulator_repository import SimulatorRepository
from app.utils import metrics as m

HEALTH_VALUE = {"healthy": 1.0, "degraded": 0.5, "down": 0.0}
STAGE_HEALTH = {"ok": "healthy", "fallback": "degraded", "skipped": "degraded", "error": "down"}
ERROR_RATE_DEGRADED = 0.05


def _stage(state: PipelineState, *names: str) -> tuple[str, str | None]:
    stages = {s.name: s for s in state.stages}
    found = [stages[n] for n in names if n in stages]
    if not found:
        return "degraded", "no pipeline run yet"
    worst = max(found, key=lambda s: 1 - HEALTH_VALUE[STAGE_HEALTH.get(s.status, "degraded")])
    return STAGE_HEALTH.get(worst.status, "degraded"), worst.detail


class StatusService:
    def __init__(self, session: AsyncSession, sim: SimulatorRepository, state: PipelineState) -> None:
        self.session = session
        self.sim = sim
        self.state = state

    async def _database(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            await self.session.execute(text("SELECT 1"))
        except Exception as exc:
            return {"status": "down", "detail": type(exc).__name__}
        ms = (time.perf_counter() - started) * 1000
        m.DATABASE_LATENCY.set(ms / 1000)
        return {"status": "healthy", "latency_ms": round(ms, 1)}

    def _simulator(self) -> dict[str, Any]:
        st, circuit = self.state, self.sim.breaker.state
        stale = bool(st.world and st.world.stale)
        if not st.sim_connected or circuit == "open":
            status = "down"
        elif stale or circuit == "half_open" or st.link != "sse":
            status = "degraded"
        else:
            status = "healthy"
        detail = self.sim.last_error or ("data flagged stale" if stale else None)
        if self.sim.last_latency_ms is not None:
            m.SIMULATOR_LATENCY.set(self.sim.last_latency_ms / 1000)
        return {"status": status, "link": st.link, "circuit": circuit, "latency_ms": self.sim.last_latency_ms,
                "detail": detail}

    async def status(self) -> dict[str, Any]:
        traffic = m.request_window.summary()
        api = "degraded" if traffic["error_rate"] > ERROR_RATE_DEGRADED else "healthy"
        predict, predict_detail = _stage(self.state, "detect", "predict")
        decide, decide_detail = _stage(self.state, "decide", "post")
        components = {
            "backend_api": {"label": "Backend API", "status": api},
            "database": {"label": "Database", **await self._database()},
            "simulator": {"label": "Fuel Simulator", **self._simulator()},
            "prediction": {"label": "Prediction Service", "status": predict, "detail": predict_detail},
            "decision": {"label": "Decision Engine", "status": decide, "detail": decide_detail},
        }
        for key, c in components.items():
            m.COMPONENT_HEALTH.labels(key).set(HEALTH_VALUE[c["status"]])
        m.PIPELINE_RUNS.set(self.state.runs)
        if self.state.last_processed_tick is not None:
            m.PIPELINE_TICK.set(self.state.last_processed_tick)
        if self.state.last_run.get("duration_ms") is not None:
            m.PIPELINE_RUN_SECONDS.set(self.state.last_run["duration_ms"] / 1000)
        statuses = [c["status"] for c in components.values()]
        overall = "down" if "down" in statuses else "degraded" if "degraded" in statuses else "healthy"
        return {"status": overall, "components": components, **traffic}
