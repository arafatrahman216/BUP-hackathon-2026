"""Generic async CRUD repository. Subclass it and set `model`."""

from typing import Any, ClassVar, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: ClassVar[type[Base]]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _base_query(self) -> Select:
        """Override to add default filters/ordering for list() and count()."""
        return select(self.model)

    async def get(self, id: Any) -> ModelT | None:
        return await self.session.get(self.model, id)

    async def list(self, *, offset: int = 0, limit: int = 100, query: Select | None = None) -> list[ModelT]:
        query = query if query is not None else self._base_query()
        result = await self.session.execute(query.offset(offset).limit(limit))
        return list(result.scalars().all())

    async def count(self, *, query: Select | None = None) -> int:
        query = query if query is not None else self._base_query()
        subquery = query.order_by(None).subquery()
        result = await self.session.execute(select(func.count()).select_from(subquery))
        return result.scalar_one()

    async def create(self, data: dict[str, Any], *, commit: bool = True) -> ModelT:
        obj = self.model(**data)
        self.session.add(obj)
        await self._save(obj, commit)
        return obj

    async def update(self, obj: ModelT, data: dict[str, Any], *, commit: bool = True) -> ModelT:
        for field, value in data.items():
            setattr(obj, field, value)
        await self._save(obj, commit)
        return obj

    async def delete(self, obj: ModelT, *, commit: bool = True) -> None:
        await self.session.delete(obj)
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

    async def _save(self, obj: ModelT, commit: bool) -> None:
        # Pass commit=False to group several writes into one transaction, then
        # call `await session.commit()` yourself.
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        await self.session.refresh(obj)
