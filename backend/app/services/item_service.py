from app.ai import LLMClient
from app.core.exceptions import ConflictError, NotFoundError
from app.models import Item
from app.repositories.item_repository import ItemRepository
from app.schemas.common import Page
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate
from app.utils.pagination import PageParams, build_page


class ItemService:
    """Business logic for items. Controllers call this; this calls the repository."""

    def __init__(self, repo: ItemRepository, llm: LLMClient) -> None:
        self.repo = repo
        self.llm = llm

    async def get(self, item_id: int) -> Item:
        item = await self.repo.get(item_id)
        if item is None:
            raise NotFoundError(f"Item {item_id} not found")
        return item

    async def list(self, params: PageParams, *, search: str | None = None, is_active: bool | None = None) -> Page[ItemRead]:
        query = self.repo.search_query(search=search, is_active=is_active)
        items = await self.repo.list(offset=params.offset, limit=params.page_size, query=query)
        total = await self.repo.count(query=query)
        return build_page([ItemRead.model_validate(i) for i in items], total, params)

    async def create(self, payload: ItemCreate) -> Item:
        await self._ensure_name_available(payload.name)
        return await self.repo.create(payload.model_dump())

    async def update(self, item_id: int, payload: ItemUpdate) -> Item:
        item = await self.get(item_id)
        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] != item.name:
            await self._ensure_name_available(data["name"])
        return await self.repo.update(item, data)

    async def delete(self, item_id: int) -> None:
        item = await self.get(item_id)
        await self.repo.delete(item)

    async def generate_description(self, item_id: int) -> Item:
        """Example of a feature that uses the AI module from a service."""
        item = await self.get(item_id)
        reply = await self.llm.complete(
            f"Write a catchy product description (max 2 sentences) for '{item.name}', priced at {item.price}.",
            system="You are a concise marketing copywriter. Reply with the description only.",
        )
        return await self.repo.update(item, {"description": reply.text.strip()})

    async def _ensure_name_available(self, name: str) -> None:
        if await self.repo.get_by_name(name):
            raise ConflictError(f"An item named '{name}' already exists", details={"field": "name"})
