from typing import Any

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TickSnapshot(TimestampMixin, Base):
    """Compact world state saved by the pipeline for one simulator tick."""

    __tablename__ = "tick_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    tick: Mapped[int] = mapped_column(Integer, index=True)
    sim_time: Mapped[str] = mapped_column(String(40))
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
    valid: Mapped[bool] = mapped_column(Boolean, default=True)
    # {"stations": {id: {status, multiplier, inventory}}, "depots": {...}, "routes": {id: status}, "metrics": {...}}
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
