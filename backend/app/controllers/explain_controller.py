from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.dependencies import get_explain_service
from app.schemas.explain import (
    ActionQuestionRead, ActionQuestions, AskRequest, ContextRequest, ContextResponse, ExplainCatalog, ExplainRequest,
    ExplainResponse,
)
from app.services.explain_service import ExplainService

router = APIRouter(prefix="/explain", tags=["explain"])

Service = Annotated[ExplainService, Depends(get_explain_service)]


@router.get("/profiles", response_model=ExplainCatalog)
async def profiles(service: Service):
    """Profiles from profiles.json and every registered metric."""
    return service.catalog()


@router.post("/context", response_model=ContextResponse)
async def context(payload: ContextRequest, service: Service):
    """The JSON context the LLM would receive, without calling it (for tuning metrics)."""
    return await service.context(payload)


@router.post("", response_model=ExplainResponse)
async def explain(payload: ExplainRequest, service: Service):
    """Answer any question with the LLM (not stored)."""
    return await service.explain(payload)


@router.get("/recommendations/{rec_id}", response_model=ActionQuestions)
async def recommendation_questions(rec_id: int, service: Service):
    """Suggested questions for this recommendation's status and the questions already asked."""
    return await service.recommendation_questions(rec_id)


@router.post("/recommendations/{rec_id}", response_model=ActionQuestionRead)
async def ask_about_recommendation(rec_id: int, payload: AskRequest, service: Service):
    """Ask about one recommendation (approval queue / decision log). The answer is stored."""
    return await service.ask_about_recommendation(rec_id, payload.question)
