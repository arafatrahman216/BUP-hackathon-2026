from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.dependencies import get_status_service
from app.schemas.status import SystemStatus
from app.services.status_service import StatusService
from app.utils.metrics import REGISTRY

router = APIRouter(tags=["status"])
Service = Annotated[StatusService, Depends(get_status_service)]


@router.get("/status", response_model=SystemStatus)
async def system_status(service: Service):
    """Health per component (healthy / degraded / down), p95 latency and error rate over the last 5 min."""
    return await service.status()


@router.get("/metrics", include_in_schema=False)
async def metrics(service: Service):
    """Prometheus exposition format (scraped by monitoring/prometheus.yml)."""
    await service.status()  # refresh the component gauges
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
