from typing import Annotated

from fastapi import APIRouter, Depends

from app.ai import LLMResponse
from app.core.dependencies import get_ai_service
from app.schemas.ai import AIStatus, ChatRequest, GenerateRequest
from app.services.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["ai"])

Service = Annotated[AIService, Depends(get_ai_service)]


@router.get("/providers", response_model=AIStatus)
async def ai_status(service: Service):
    """Shows the configured chain and which providers have credentials."""
    return service.status()


@router.post("/chat", response_model=LLMResponse)
async def chat(payload: ChatRequest, service: Service):
    return await service.chat(payload)


@router.post("/generate", response_model=LLMResponse)
async def generate(payload: GenerateRequest, service: Service):
    return await service.generate(payload)
