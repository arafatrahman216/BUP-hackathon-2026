from typing import Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ActionQuestion(TimestampMixin, Base):
    """A question an operator asked about a recommendation, the LLM's answer and the context it was given."""

    __tablename__ = "action_questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("recommendations.id"), index=True)
    tick: Mapped[int | None] = mapped_column(Integer, nullable=True)  # simulator tick when asked
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    profile: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    context: Mapped[dict[str, Any]] = mapped_column(JSON)  # exactly what the LLM received
    errors: Mapped[list[Any]] = mapped_column(JSON, default=list)  # metrics that could not be computed
