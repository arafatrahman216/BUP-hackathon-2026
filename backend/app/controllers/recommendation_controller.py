from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.dependencies import get_recommendation_service
from app.schemas.common import Page
from app.schemas.recommendation import ApproveRequest, RecommendationRead, RejectRequest
from app.services.recommendation_service import RecommendationService
from app.utils.pagination import PageParams, build_page, page_params

router = APIRouter(prefix="/recommendations", tags=["recommendations"])
Service = Annotated[RecommendationService, Depends(get_recommendation_service)]


@router.get("", response_model=Page[RecommendationRead])
async def list_recommendations(service: Service, params: PageParams = Depends(page_params),
                               status: str | None = Query(None, description="e.g. PENDING_APPROVAL, POSTED")):
    items, total = await service.list(params.offset, params.page_size, status)
    return build_page(items, total, params)


@router.get("/{rec_id}", response_model=RecommendationRead)
async def get_recommendation(rec_id: int, service: Service):
    return await service.get(rec_id)


@router.post("/{rec_id}/approve", response_model=RecommendationRead)
async def approve(rec_id: int, body: ApproveRequest, service: Service):
    """Approve (optionally with an edited quantity) and post to the simulator right away."""
    return await service.approve(rec_id, body.quantity, body.note)


@router.post("/{rec_id}/reject", response_model=RecommendationRead)
async def reject(rec_id: int, body: RejectRequest, service: Service):
    return await service.reject(rec_id, body.note)
