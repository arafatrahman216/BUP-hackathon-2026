from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DashboardState(BaseModel):
    """Everything the operator dashboard shows. Same payload as the `state` SSE event."""

    sim: dict[str, Any]
    pipeline: dict[str, Any]
    alerts: list[dict[str, Any]]
    incidents: list[dict[str, Any]] = []
    outlook: dict[str, Any] = {}
    blocked: list[dict[str, Any]]
    recommendations: dict[str, list[dict[str, Any]]]
    stations: list[dict[str, Any]]
    depots: list[dict[str, Any]]
    routes: list[dict[str, Any]]
    supply: list[dict[str, Any]]
    events: list[dict[str, Any]]
    allocations: list[dict[str, Any]]
    metrics: dict[str, Any]


class SnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tick: int
    sim_time: str
    stale: bool
    valid: bool
    data: dict[str, Any]
    created_at: datetime


class RunResult(BaseModel):
    ran: bool
    tick: int | None
    detail: str | None = None
