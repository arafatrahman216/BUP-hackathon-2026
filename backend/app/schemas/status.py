from typing import Literal

from pydantic import BaseModel

Health = Literal["healthy", "degraded", "down"]


class ComponentStatus(BaseModel):
    label: str
    status: Health
    detail: str | None = None
    latency_ms: float | None = None
    link: str | None = None  # simulator only
    circuit: str | None = None  # simulator only


class SystemStatus(BaseModel):
    status: Health  # worst component
    components: dict[str, ComponentStatus]
    requests: int  # in the window
    p95_latency_ms: float | None
    error_rate: float  # 5xx / requests in the window
    window_seconds: int
