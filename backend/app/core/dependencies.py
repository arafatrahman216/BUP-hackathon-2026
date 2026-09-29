"""Dependency wiring: builds services (with their repositories) for controllers.

Add a `get_<feature>_service` here for each new feature.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import LLMClient, get_llm_client
from app.core.database import get_db
from app.repositories.storage_repository import StorageRepository, get_storage_repository
from app.services.ai_service import AIService

DbSession = Annotated[AsyncSession, Depends(get_db)]
LLM = Annotated[LLMClient, Depends(get_llm_client)]
Storage = Annotated[StorageRepository, Depends(get_storage_repository)]


def get_ai_service(llm: LLM) -> AIService:
    return AIService(llm)
