"""Import every model here so Base.metadata knows about it (needed for create_all)."""

from app.models.base import Base, TimestampMixin

__all__ = ["Base", "TimestampMixin"]
