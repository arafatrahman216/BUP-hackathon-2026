"""In-memory pipeline state: the last good world, forecasts, alerts, stage health,
and the broadcaster that pushes updates to dashboard SSE subscribers.

The backend owns this cache, so the dashboard keeps working (marked stale) when
the simulator is down. It is per-process; run one backend instance.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from app.pipeline.types import Alert, Blocked, Forecast, World


@dataclass
class StageResult:
    name: str
    status: str = "pending"  # ok | fallback | skipped | error
    ms: float = 0.0
    detail: str | None = None


@dataclass
class PipelineState:
    world: World | None = None
    world_read_at: float | None = None  # time.time() of the last successful read
    last_processed_tick: int | None = None
    forecasts: dict[tuple[str, str], Forecast] = field(default_factory=dict)
    rates: dict[tuple[str, str], float | None] = field(default_factory=dict)
    alerts: list[Alert] = field(default_factory=list)
    blocked: list[Blocked] = field(default_factory=list)
    validation_issues: list[str] = field(default_factory=list)
    acting: bool = False  # false -> data stale/invalid, decide + post were skipped
    stages: list[StageResult] = field(default_factory=list)
    last_run: dict[str, Any] = field(default_factory=dict)
    runs: int = 0
    sim_connected: bool = False
    sim_error: str | None = None
    link: str = "starting"  # sse | polling | down
    recommendations: dict[str, list[dict[str, Any]]] = field(default_factory=lambda: {"open": [], "recent": []})
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # decide/post vs operator actions
    run_lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # one pipeline run at a time
    _subscribers: set[asyncio.Queue] = field(default_factory=set)

    # --- broadcasting ---
    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=5)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: str = "state", data: Any = None) -> None:
        message = f"event: {event}\ndata: {json.dumps(data if data is not None else self.to_dashboard(), default=str)}\n\n"
        for queue in list(self._subscribers):
            if queue.full():  # slow client: drop its oldest message, keep the newest
                queue.get_nowait()
            queue.put_nowait(message)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    # --- dashboard payload ---
    def to_dashboard(self) -> dict[str, Any]:
        w = self.world
        age = round(time.time() - self.world_read_at, 1) if self.world_read_at else None
        payload: dict[str, Any] = {
            "sim": {
                "connected": self.sim_connected, "link": self.link, "error": self.sim_error,
                "stale": (w.stale if w else True) or not self.sim_connected, "data_age_seconds": age,
                "tick": w.tick if w else None, "sim_time": w.instance.get("sim_time") if w else None,
                "status": w.instance.get("status") if w else None, "tick_minutes": w.tick_minutes if w else None,
            },
            "pipeline": {
                "acting": self.acting, "runs": self.runs, "last_run": self.last_run,
                "stages": [s.__dict__ for s in self.stages], "validation_issues": self.validation_issues,
            },
            "alerts": [a.to_dict() for a in self.alerts],
            "blocked": [b.__dict__ for b in self.blocked],
            "recommendations": self.recommendations,
            "stations": [], "depots": [], "routes": [], "supply": [], "events": [], "allocations": [], "metrics": {},
        }
        if not w:
            return payload
        payload["stations"] = [
            {**{k: s.get(k) for k in ("id", "name", "region_id", "status", "demand_profile", "demand_multiplier")},
             "fuels": [self.forecasts[(sid, f)].to_dict() for f in w.fuel_types if (sid, f) in self.forecasts]}
            for sid, s in w.stations.items()
        ]
        payload["depots"] = [
            {**{k: d.get(k) for k in ("id", "name", "region_id", "status", "dispatch_capacity_per_tick")},
             "dispatch_used": w.dispatch_used(did),
             "fuels": [{"fuel_type": f, "inventory": d["inventory"].get(f, 0), "capacity": d["capacity"].get(f, 0)}
                       for f in sorted(d.get("inventory", {}))]}
            for did, d in w.depots.items()
        ]
        payload["routes"] = list(w.routes.values())
        payload["supply"] = [a for a in w.supply if a.get("status") != "ARRIVED"][:12]
        payload["events"] = [e for e in w.events if e.get("status") != "RESOLVED"]
        active = [a for a in w.allocations if a.get("status") in ("PENDING", "IN_TRANSIT")]
        payload["allocations"] = active + [a for a in w.allocations if a not in active][:10]
        payload["metrics"] = w.metrics
        return payload


_state: PipelineState | None = None


def get_pipeline_state() -> PipelineState:
    global _state
    if _state is None:
        _state = PipelineState()
    return _state


def reset_pipeline_state() -> None:
    global _state
    _state = None
