"""Explainability: gather the pipeline's view of the world for a question, then ask the LLM.

Data comes from the tick pipeline's cache (the world it last read, its forecasts and alerts),
so an explanation uses the same numbers the system decided with. With no cache yet (the
pipeline hasn't run), it reads the simulator through the same read / predict / detect code.
"""

import time
from typing import Any

from app.ai import LLMClient
from app.core.config import Settings
from app.core.exceptions import BadRequestError, NotFoundError, ServiceUnavailableError
from app.explainability import (
    METRICS, BuiltContext, MetricContext, Profile, ProfileBook, Snapshot, Subject, build_context, build_messages,
    load_profiles,
)
from app.explainability.context import unknown_metrics
from app.models.action_question import ActionQuestion
from app.pipeline.detect import detect, stockout_alerts
from app.pipeline.predict import Predictor
from app.pipeline.state import PipelineState
from app.repositories.action_question_repository import ActionQuestionRepository
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.simulator_repository import SimulatorError, SimulatorRejection, SimulatorRepository
from app.schemas.explain import (
    ActionQuestions, ContextRequest, ContextResponse, ExplainCatalog, ExplainRequest, ExplainResponse, MetricInfo,
    ProfileInfo,
)
from app.schemas.recommendation import RecommendationRead
from app.services.pipeline_service import read_world
from app.utils.logger import get_logger

logger = get_logger(__name__)

RECOMMENDATION_PROFILE = "recommendation"
# pipeline settings the `risk_rules` metric explains
RULE_SETTINGS = (
    "FORECAST_WINDOW_TICKS", "SAFETY_TICKS", "URGENT_MARGIN_TICKS", "MIN_SHIPMENT_LITERS", "DEPOT_RESERVE_LITERS",
    "AUTO_POST_ENABLED", "APPROVAL_TTL_TICKS", "APPROVAL_MIN_SECONDS", "STALE_DATA_MODE", "STALE_QUANTITY_FACTOR",
    "PREDICTOR", "PLANNER", "FORECAST_HORIZON_TICKS", "MIN_CONFIDENCE_AUTO", "RATIONING_TRIGGER_DAYS",
    "URGENT_REVIEW_DEPOT_SHARE",
)
SIM_ERRORS = (SimulatorError, SimulatorRejection)


def _rec_dict(rec: Any) -> dict[str, Any]:
    return RecommendationRead.model_validate(rec).model_dump(mode="json", exclude={"idempotency_key", "updated_at"})


class ExplainService:
    def __init__(self, sim: SimulatorRepository, recs: RecommendationRepository, questions: ActionQuestionRepository,
                 state: PipelineState, llm: LLMClient, predictor: Predictor, settings: Settings) -> None:
        self.sim = sim
        self.recs = recs
        self.questions = questions
        self.state = state
        self.llm = llm
        self.predictor = predictor
        self.settings = settings

    def _book(self) -> ProfileBook:
        return load_profiles(self.settings.EXPLAIN_PROFILES_PATH or None)

    # ---------- public ----------
    def catalog(self) -> ExplainCatalog:
        book = self._book()
        return ExplainCatalog(
            default_profile=book.default_profile,
            params=book.params,
            profiles={n: ProfileInfo(description=p.description, metrics=p.metrics, instructions=p.instructions,
                                     suggested_questions=p.suggested_questions) for n, p in book.profiles.items()},
            metrics=[MetricInfo(name=m.name, description=m.description) for m in METRICS.values()],
        )

    async def context(self, req: ContextRequest) -> ContextResponse:
        profile, metrics, snapshot, built = await self._gather(req)
        return ContextResponse(profile=profile.name, metrics=metrics, data_source=snapshot.source,
                               tick=snapshot.world.tick, context=built.context, errors=built.errors)

    async def explain(self, req: ExplainRequest) -> ExplainResponse:
        profile, metrics, snapshot, built = await self._gather(req)
        reply = await self.llm.chat(
            build_messages(req.question, profile, built.context),
            provider=self.settings.EXPLAIN_PROVIDER or None,
            model=self.settings.EXPLAIN_MODEL or None,
            temperature=self.settings.EXPLAIN_TEMPERATURE,
            max_tokens=self.settings.EXPLAIN_MAX_TOKENS,
        )
        return ExplainResponse(
            profile=profile.name, metrics=metrics, data_source=snapshot.source, tick=snapshot.world.tick,
            context=built.context, errors=built.errors, question=req.question, answer=reply.text.strip(),
            provider=reply.provider, model=reply.model, attempts=reply.attempts,
        )

    async def ask_about_recommendation(self, rec_id: int, question: str) -> ActionQuestion:
        """The "Ask" button on an approval card / decision-log row. The Q&A is stored."""
        await self._recommendation(rec_id)
        result = await self.explain(ExplainRequest(question=question, profile=RECOMMENDATION_PROFILE,
                                                   recommendation_id=rec_id))
        return await self.questions.create({
            "recommendation_id": rec_id, "tick": result.tick, "question": question, "answer": result.answer,
            "profile": result.profile, "provider": result.provider, "model": result.model,
            "context": result.context, "errors": [e.model_dump() for e in result.errors],
        })

    async def recommendation_questions(self, rec_id: int) -> ActionQuestions:
        rec = await self._recommendation(rec_id)
        profile = self._book().profiles.get(RECOMMENDATION_PROFILE)
        return ActionQuestions(
            recommendation_id=rec_id, status=rec.status,
            suggestions=profile.suggestions(rec.status) if profile else [],
            items=await self.questions.list_for(rec_id),
        )

    # ---------- steps ----------
    async def _recommendation(self, rec_id: int) -> Any:
        rec = await self.recs.get(rec_id)
        if rec is None:
            raise NotFoundError(f"Recommendation {rec_id} not found")
        return rec

    async def _gather(self, req: ContextRequest) -> tuple[Profile, list[str], Snapshot, BuiltContext]:
        book = self._book()
        name = req.profile or book.default_profile
        profile = book.profiles.get(name)
        if profile is None:
            raise BadRequestError(f"Unknown profile {name!r}", code="UNKNOWN_PROFILE", details=sorted(book.profiles))
        metrics = req.metrics if req.metrics is not None else profile.metrics
        if bad := unknown_metrics(metrics):
            raise BadRequestError(f"Unknown metrics: {', '.join(bad)}", code="UNKNOWN_METRIC", details=sorted(METRICS))

        snapshot = await self._snapshot()
        action = await self._action(req, snapshot)
        subject = Subject.build(action, station_id=req.station_id, fuel_type=req.fuel_type,
                                depot_id=req.depot_id, route_id=req.route_id)
        notes: list[str] = []
        if snapshot.source == "live":
            notes.append("the pipeline has not run yet: data was read live and forecast with the same rules")
        if action and action.get("tick") is not None and int(action["tick"]) != snapshot.world.tick:
            notes.append(f"the action was proposed at tick {action['tick']}; all other data is from the current "
                         f"tick {snapshot.world.tick}, not from the moment it was decided")

        history = None
        if subject.station_id and "demand" in metrics:
            try:
                history = (await self.sim.demand_history(self.settings.EXPLAIN_HISTORY_LIMIT,
                                                         station_id=subject.station_id)).data
            except SIM_ERRORS as exc:
                logger.warning("explain: longer demand history unavailable: %s", exc)
                notes.append(f"longer demand history unavailable; `demand` uses the pipeline's last "
                             f"{self.settings.FORECAST_WINDOW_TICKS} ticks")
        try:
            open_recs = [_rec_dict(r) for r in await self.recs.list_open()]
        except Exception as exc:  # DB down: explain without them
            logger.warning("explain: open recommendations unavailable: %s", exc)
            open_recs = []
            notes.append("open recommendations unavailable (database error)")

        ctx = MetricContext(
            snapshot=snapshot, subject=subject, params={**book.params, **(req.params or {})},
            rules={k: getattr(self.settings, k) for k in RULE_SETTINGS}, open_recommendations=open_recs,
            history=history,
        )
        return profile, metrics, snapshot, build_context(metrics, ctx, notes)

    async def _snapshot(self) -> Snapshot:
        """The pipeline's cached world + forecasts + alerts; a live read through the same
        read / predict / detect code when there is no cache yet."""
        st = self.state
        if st.world is not None:
            age = time.time() - st.world_read_at if st.world_read_at else None
            forecasts = st.forecasts or self.predictor.predict(st.world)
            incidents = list(reversed(st.detector.incidents[-10:])) if st.detector else []
            return Snapshot(st.world, forecasts, list(st.alerts), list(st.blocked), "pipeline_cache", age,
                            outlook=dict(st.outlook), planner_info=dict(st.planner_info), incidents=incidents)
        try:
            world = await read_world(self.sim, self.settings)
        except SIM_ERRORS as exc:
            raise ServiceUnavailableError(f"Simulator is unreachable and there is no cached state: {exc}",
                                          code="SIMULATOR_UNAVAILABLE") from exc
        forecasts = self.predictor.predict(world)
        return Snapshot(world, forecasts, detect(world) + stockout_alerts(forecasts), [], "live", 0.0,
                        outlook=dict(getattr(self.predictor, "outlook", {}) or {}))

    async def _action(self, req: ContextRequest, snapshot: Snapshot) -> dict[str, Any] | None:
        if req.action is not None:
            return req.action
        if req.recommendation_id is not None:
            rec = await self._recommendation(req.recommendation_id)
            return {"kind": "recommendation", **_rec_dict(rec),
                    "ticks_since_proposed": snapshot.world.tick - rec.tick}
        if req.allocation_id is not None:
            found = next((a for a in snapshot.world.allocations if a.get("id") == req.allocation_id), None)
            if found is None:
                raise NotFoundError(f"Allocation {req.allocation_id} not found")
            return {"kind": "allocation", **{k: v for k, v in found.items() if k != "idempotency_key"}}
        return None
