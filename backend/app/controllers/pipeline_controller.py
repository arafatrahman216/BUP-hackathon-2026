from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_dashboard_service, get_pipeline_service, get_stream_service
from app.schemas.common import Page
from app.schemas.pipeline import DashboardState, RunResult, SnapshotRead
from app.services.dashboard_service import DashboardService
from app.services.pipeline_service import PipelineService
from app.utils.pagination import PageParams, build_page, page_params

router = APIRouter(tags=["pipeline"])
Dashboard = Annotated[DashboardService, Depends(get_dashboard_service)]
Stream = Annotated[DashboardService, Depends(get_stream_service)]
Pipeline = Annotated[PipelineService, Depends(get_pipeline_service)]


@router.get("/dashboard", response_model=DashboardState)
async def dashboard(service: Dashboard):
    """Latest cached state (works while the simulator is down; see `sim.stale`)."""
    return service.current()


@router.get("/stream", response_class=StreamingResponse)
async def stream(service: Stream):
    """SSE for the dashboard: `state` events (full DashboardState) and `depot` hints."""
    return StreamingResponse(service.stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/pipeline/run", response_model=RunResult)
async def run_pipeline(service: Pipeline):
    """Run the pipeline now, even if this tick was already processed."""
    return await service.run(force=True)


@router.get("/snapshots", response_model=Page[SnapshotRead])
async def snapshots(service: Dashboard, params: PageParams = Depends(page_params)):
    items, total = await service.list_snapshots(params.offset, params.page_size)
    return build_page(items, total, params)
