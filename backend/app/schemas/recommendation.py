from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tick: int
    station_id: str
    fuel_type: str
    depot_id: str
    route_id: str
    quantity: float
    proposed_quantity: float
    risk: str
    ticks_until_empty: float | None
    important: bool
    decision_mode: str
    reasons: list[str]
    explanation: str
    planner: str
    status: str
    operator_note: str | None
    idempotency_key: str | None
    allocation_id: int | None
    posted_tick: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ApproveRequest(BaseModel):
    quantity: float | None = Field(None, gt=0, description="Edited quantity in liters; omit to keep the proposal")
    note: str | None = Field(None, max_length=500)


class RejectRequest(BaseModel):
    note: str | None = Field(None, max_length=500)
