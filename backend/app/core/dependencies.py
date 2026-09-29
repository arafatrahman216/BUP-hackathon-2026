"""Dependency wiring: builds services (with their repositories) for controllers.

Add a `get_<feature>_service` here for each new feature.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import LLMClient, get_llm_client
from app.core.config import get_settings
from app.core.database import get_db
from app.repositories.item_repository import ItemRepository
from app.repositories.storage_repository import StorageRepository, get_storage_repository
from app.services.ai_service import AIService
from app.services.file_service import FileService
from app.services.item_service import ItemService

DbSession = Annotated[AsyncSession, Depends(get_db)]
LLM = Annotated[LLMClient, Depends(get_llm_client)]
Storage = Annotated[StorageRepository, Depends(get_storage_repository)]


def get_item_service(session: DbSession, llm: LLM) -> ItemService:
    return ItemService(ItemRepository(session), llm)


def get_ai_service(llm: LLM) -> AIService:
    return AIService(llm)


def get_file_service(storage: Storage) -> FileService:
    return FileService(storage, get_settings().MAX_UPLOAD_MB)
