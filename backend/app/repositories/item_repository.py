from sqlalchemy import select
from sqlalchemy.sql import Select

from app.models import Item
from app.repositories.base_repository import BaseRepository


class ItemRepository(BaseRepository[Item]):
    model = Item

    def _base_query(self) -> Select:
        return select(Item).order_by(Item.id)

    def search_query(self, *, search: str | None = None, is_active: bool | None = None) -> Select:
        query = self._base_query()
        if search:
            query = query.where(Item.name.ilike(f"%{search}%"))
        if is_active is not None:
            query = query.where(Item.is_active == is_active)
        return query

    async def get_by_name(self, name: str) -> Item | None:
        result = await self.session.execute(select(Item).where(Item.name == name))
        return result.scalar_one_or_none()
