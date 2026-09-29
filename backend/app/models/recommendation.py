from typing import Any

from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RecommendationStatus:
    PENDING_APPROVAL = "PENDING_APPROVAL"  # important: waits for the operator
    APPROVED = "APPROVED"  # approved (by operator or auto) but not posted yet, e.g. simulator down
    POSTED = "POSTED"  # accepted by the simulator (allocation_id set)
    REFUSED = "REFUSED"  # simulator answered 4xx (error_code set)
    REJECTED = "REJECTED"  # operator rejected
    EXPIRED = "EXPIRED"  # nobody answered within APPROVAL_TTL_TICKS

    OPEN = (PENDING_APPROVAL, APPROVED)


class Recommendation(TimestampMixin, Base):
    """One shipment proposal (depot -> station over a route) and what happened to it."""

    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    tick: Mapped[int] = mapped_column(Integer, index=True)
    station_id: Mapped[str] = mapped_column(String(64), index=True)
    fuel_type: Mapped[str] = mapped_column(String(16))
    depot_id: Mapped[str] = mapped_column(String(64))
    route_id: Mapped[str] = mapped_column(String(64))
    quantity: Mapped[float] = mapped_column(Float)
    proposed_quantity: Mapped[float] = mapped_column(Float)  # before any operator edit
    risk: Mapped[str] = mapped_column(String(16))  # safe | watch | urgent
    ticks_until_empty: Mapped[float | None] = mapped_column(Float, nullable=True)
    important: Mapped[bool] = mapped_column(Boolean, default=False)
    decision_mode: Mapped[str] = mapped_column(String(16))  # auto | operator
    reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)  # why it is important
    explanation: Mapped[str] = mapped_column(Text, default="")
    planner: Mapped[str] = mapped_column(String(32), default="rules")
    status: Mapped[str] = mapped_column(String(24), index=True)
    operator_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(150), nullable=True)
    allocation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    posted_tick: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
