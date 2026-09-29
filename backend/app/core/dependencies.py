"""Dependency wiring: builds services (with their repositories) for controllers.

Add a `get_<feature>_service` here for each new feature.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import pipeline
from app.ai import LLMClient, get_llm_client
from app.core.config import get_settings
from app.core.database import get_db
from app.pipeline.state import PipelineState, get_pipeline_state
from app.repositories.action_question_repository import ActionQuestionRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.simulator_repository import SimulatorRepository, get_simulator_repository
from app.repositories.snapshot_repository import SnapshotRepository
from app.repositories.storage_repository import StorageRepository, get_storage_repository
from app.services.ai_service import AIService
from app.services.dashboard_service import DashboardService
from app.services.explain_service import ExplainService
from app.services.pipeline_service import PipelineService
from app.services.recommendation_service import RecommendationService
from app.services.status_service import StatusService

DbSession = Annotated[AsyncSession, Depends(get_db)]
LLM = Annotated[LLMClient, Depends(get_llm_client)]
Storage = Annotated[StorageRepository, Depends(get_storage_repository)]
Simulator = Annotated[SimulatorRepository, Depends(get_simulator_repository)]
State = Annotated[PipelineState, Depends(get_pipeline_state)]


def get_ai_service(llm: LLM) -> AIService:
    return AIService(llm)


def get_recommendation_service(session: DbSession, sim: Simulator, state: State) -> RecommendationService:
    return RecommendationService(RecommendationRepository(session), sim, state, get_settings())


def build_pipeline_service(session: AsyncSession, sim: SimulatorRepository, state: PipelineState) -> PipelineService:
    """Also used by the background tick watcher (outside a request)."""
    settings = get_settings()
    recs = RecommendationRepository(session)
    return PipelineService(
        sim, SnapshotRepository(session), recs, RecommendationService(recs, sim, state, settings), state, settings,
        predictor=pipeline.build_predictor(settings, state),
        planner=pipeline.build_planner(settings),
        fallback_planner=pipeline.build_fallback_planner(settings),
        explainer=pipeline.build_explainer(settings),
    )


def get_pipeline_service(session: DbSession, sim: Simulator, state: State) -> PipelineService:
    return build_pipeline_service(session, sim, state)


def get_dashboard_service(session: DbSession, state: State) -> DashboardService:
    return DashboardService(state, SnapshotRepository(session))


def get_stream_service(state: State) -> DashboardService:
    """No DB session: an SSE connection stays open for a long time."""
    return DashboardService(state)


def get_status_service(session: DbSession, sim: Simulator, state: State) -> StatusService:
    return StatusService(session, sim, state)


def get_explain_service(session: DbSession, sim: Simulator, state: State, llm: LLM) -> ExplainService:
    settings = get_settings()
    return ExplainService(sim, RecommendationRepository(session), ActionQuestionRepository(session), state, llm,
                          pipeline.build_predictor(settings, state), settings)
