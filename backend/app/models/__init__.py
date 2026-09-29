"""Import every model here so Base.metadata knows about it (needed for create_all)."""

from app.models.action_question import ActionQuestion
from app.models.base import Base, TimestampMixin
from app.models.recommendation import Recommendation, RecommendationStatus
from app.models.snapshot import TickSnapshot

__all__ = ["ActionQuestion", "Base", "Recommendation", "RecommendationStatus", "TickSnapshot", "TimestampMixin"]
