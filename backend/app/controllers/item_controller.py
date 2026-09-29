from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import get_item_service
from app.schemas.common import Page
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate
from app.services.item_service import ItemService
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/items", tags=["items"])

Service = Annotated[ItemService, Depends(get_item_service)]


@router.get("", response_model=Page[ItemRead])
async def list_items(
    service: Service,
    params: Annotated[PageParams, Depends(page_params)],
    search: Annotated[str | None, Query(description="Case-insensitive name filter")] = None,
    is_active: bool | None = None,
):
    return await service.list(params, search=search, is_active=is_active)


@router.get("/{item_id}", response_model=ItemRead)
async def get_item(item_id: int, service: Service):
    return await service.get(item_id)


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemCreate, service: Service):
    return await service.create(payload)


@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(item_id: int, payload: ItemUpdate, service: Service):
    return await service.update(item_id, payload)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: int, service: Service) -> None:
    await service.delete(item_id)


@router.post("/{item_id}/generate-description", response_model=ItemRead)
async def generate_item_description(item_id: int, service: Service):
    """Fills the item's description using the AI module."""
    return await service.generate_description(item_id)
