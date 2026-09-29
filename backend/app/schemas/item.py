from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ItemBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    price: float = Field(default=0.0, ge=0)
    is_active: bool = True


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    """Partial update: only fields present in the request body are changed."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    price: float | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @field_validator("name", "price", "is_active")
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError("may not be null")
        return value


class ItemRead(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
