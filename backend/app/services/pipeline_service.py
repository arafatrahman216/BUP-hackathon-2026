"""One pipeline pass per simulator tick:

    read -> validate -> save -> detect -> predict -> decide -> explain
         -> (important? operator approves/edits/rejects : auto) -> post

Every stage records ok / fallback / skipped / error and its duration in the
pipeline state, which the dashboard shows. Fallbacks:
- read fails      -> keep the last good world, mark it stale, don't act
- validate fails  -> alert, don't act (decide + post skipped)
- save fails      -> log it and keep going (state stays in memory)
- predict fails   -> reuse the last known demand rates
- decide fails    -> fallback planner (rules); explain fails -> fallback template
- post fails      -> recommendation stays APPROVED and is retried next tick
"""

import asyncio
import time
from datetime import datetime, timezone
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import Settings
from app.models.recommendation import RecommendationStatus
from app.pipeline.decide import Planner, importance_reasons
from app.pipeline.detect import detect
from app.pipeline.explain import TemplateExplainer
from app.pipeline.predict import LastKnownRatePredictor, Predictor
from app.pipeline.state import PipelineState, StageResult
from app.pipeline.types import Alert, World
from app.pipeline.validate import validate_world
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.simulator_repository import SimulatorRepository
from app.repositories.snapshot_repository import SnapshotRepository
from app.services.recommendation_service import RecommendationService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PipelineService:
    def __init__(
        self,
        sim: SimulatorRepository,
        snapshots: SnapshotRepository,
        recs: RecommendationRepository,
        rec_service: RecommendationService,
        state: PipelineState,
        settings: Settings,
        *,
        predictor: Predictor,
        planner: Planner,
        fallback_planner: Planner,
        explainer: Any,
        fallback_explainer: Any = None,
    ) -> None:
        self.sim = sim
        self.snapshots = snapshots
        self.recs = recs
        self.rec_service = rec_service
        self.state = state
        self.settings = settings
        self.predictor = predictor
        self.planner = planner
        self.fallback_planner = fallback_planner
        self.explainer = explainer
        self.fallback_explainer = fallback_explainer or TemplateExplainer()

    async def run(self, force: bool = False) -> dict[str, Any]:
        async with self.state.run_lock:  # one run at a time (watcher + manual runs)
            return await self._run(force)

    async def _run(self, force: bool) -> dict[str, Any]:
        state, s = self.state, self.settings
        started = time.perf_counter()
        stages: list[StageResult] = []

        async def stage(name: str, fn: Callable[[], Awaitable[Any]]) -> tuple[Any, StageResult]:
            result = StageResult(name)
            t0 = time.perf_counter()
            try:
                value = await fn()
                result.status = "ok"
            except Exception as exc:  # each stage decides its own fallback below
                logger.exception("Pipeline stage %s failed", name)
                value, result.status, result.detail = exc, "error", f"{type(exc).__name__}: {exc}"[:300]
            result.ms = round((time.perf_counter() - t0) * 1000, 1)
            stages.append(result)
            return value, result

        def skip(*names: str, why: str) -> None:
            stages.extend(StageResult(n, "skipped", 0.0, why) for n in names)

        # 1. read
        world, read = await stage("read", self._read)
        if read.status == "error":
            state.sim_connected, state.sim_error = False, read.detail
            state.acting = False
            if state.world:
                state.world.stale = True
            state.alerts = [Alert("critical", "SIMULATOR_UNREACHABLE",
                                  f"Simulator unreachable, showing cached state: {read.detail}")]
            skip("validate", "save", "detect", "predict", "decide", "explain", "post", why="no fresh data")
            return self._finish(stages, started, None)
        state.sim_connected, state.sim_error = True, None

        tick = world.tick
        if not force and tick == state.last_processed_tick:
            return {"ran": False, "tick": tick, "detail": "tick already processed"}
        reset = state.last_processed_tick is not None and tick < state.last_processed_tick
        state.world, state.world_read_at = world, time.time()

        # 2. validate
        (issues, fatal), val = await stage("validate", lambda: _async(validate_world, world))
        state.validation_issues = issues
        state.acting = not fatal
        if fatal:
            val.status, val.detail = "fallback", "invalid or stale data: not acting this tick"

        # 3. save
        if s.SNAPSHOT_EVERY_TICKS > 0 and (state.runs % s.SNAPSHOT_EVERY_TICKS == 0):
            await stage("save", lambda: self._save(world, not fatal))
        else:
            skip("save", why=f"every {s.SNAPSHOT_EVERY_TICKS} ticks")

        # 4. detect
        alerts, det = await stage("detect", lambda: _async(detect, world))
        alerts = alerts if det.status == "ok" else []
        if reset:
            alerts.insert(0, Alert("warning", "SIMULATOR_RESET",
                                   f"Tick went back from {state.last_processed_tick} to {tick}; state resynced"))
        alerts += [Alert("warning", "DATA_INVALID", issue) for issue in issues]

        # 5. predict (fallback: last known rates)
        forecasts, pred = await stage("predict", lambda: _async(self.predictor.predict, world))
        if pred.status == "error":
            forecasts = LastKnownRatePredictor(state.rates, s.SAFETY_TICKS, s.URGENT_MARGIN_TICKS).predict(world)
            pred.status = "fallback"
        state.forecasts = forecasts
        state.rates.update({k: f.rate_per_tick for k, f in forecasts.items() if f.rate_per_tick is not None})
        for f in forecasts.values():
            if f.risk == "urgent":
                alerts.append(Alert("critical", "STOCKOUT_RISK",
                                    f"{f.station_id} {f.fuel_type} covers {f.cover_ticks:.1f} ticks, "
                                    f"lead time {f.lead_ticks} ticks", f.station_id))
        state.alerts = alerts

        # 6-7. decide + explain, then post. Only this part shares the lock with operator actions.
        async with state.lock:
            try:
                open_recs = await self.recs.list_open()
            except Exception as exc:  # DB down: we can't dedupe or persist, so don't act
                logger.exception("Could not load open recommendations")
                open_recs, state.acting = [], False
                state.validation_issues.append(f"database unavailable: {type(exc).__name__}")
            if reset:
                open_recs = await self._expire_open(open_recs, tick, everything=True)
            if not state.acting:
                skip("decide", "explain", "post", why="data stale or invalid")
            else:
                open_recs = await self._expire_open(open_recs, tick)
                plans, dec = await stage("decide", lambda: _async(self._decide, world, forecasts, open_recs))
                if dec.status == "error":
                    try:
                        plans = self._decide(world, forecasts, open_recs, fallback=True)
                        dec.status = "fallback"
                    except Exception:
                        logger.exception("Fallback planner failed too")
                        plans = []
                dec.detail = dec.detail or f"{len(plans)} new, {len(state.blocked)} blocked"
                created, exp = await stage("explain", lambda: self._explain_and_store(world, forecasts, plans))
                if exp.status == "ok":
                    open_recs += created
                posted, post = await stage("post", lambda: self._post_approved(open_recs))
                if post.status == "ok":
                    post.detail = f"{posted['posted']} posted, {posted['refused']} refused, {posted['waiting']} waiting"
                    if posted["waiting"]:
                        post.status = "fallback"

        state.last_processed_tick = tick
        await self._refresh_recs(stages)
        return self._finish(stages, started, tick)

    # ---------- stages ----------
    async def _read(self) -> World:
        names = ("instance", "depots", "stations", "routes", "supply_arrivals", "events", "allocations", "metrics")
        responses = await asyncio.gather(*(getattr(self.sim, n)() for n in names))
        by_name = dict(zip(names, responses))
        stations = by_name["stations"].data
        fuels = {f for st in stations for f in st.get("capacity", {})} or {"x"}
        history = await self.sim.demand_history(limit=len(stations) * len(fuels) * self.settings.FORECAST_WINDOW_TICKS)
        return World(
            instance=by_name["instance"].data,
            depots={d["id"]: d for d in by_name["depots"].data},
            stations={st["id"]: st for st in stations},
            routes={r["id"]: r for r in by_name["routes"].data},
            supply=by_name["supply_arrivals"].data,
            events=by_name["events"].data,
            allocations=by_name["allocations"].data,
            history=history.data,
            metrics=by_name["metrics"].data,
            stale=any(r.stale for r in (*responses, history)),
        )

    async def _save(self, world: World, valid: bool) -> None:
        pick = lambda d, keys: {k: d.get(k) for k in keys}  # noqa: E731
        await self.snapshots.create({
            "tick": world.tick, "sim_time": str(world.instance.get("sim_time")), "stale": world.stale, "valid": valid,
            "data": {
                "stations": {i: pick(st, ("status", "demand_multiplier", "inventory")) for i, st in world.stations.items()},
                "depots": {i: pick(d, ("status", "inventory")) for i, d in world.depots.items()},
                "routes": {i: r.get("status") for i, r in world.routes.items()},
                "active_events": [e.get("id") for e in world.events if e.get("status") == "ACTIVE"],
                "metrics": world.metrics,
            },
        })

    def _decide(self, world: World, forecasts: dict, open_recs: list, fallback: bool = False) -> list:
        planner = self.fallback_planner if fallback else self.planner
        skip = {(r.station_id, r.fuel_type) for r in open_recs}
        plans, blocked = planner.plan(world, forecasts, skip)
        for plan in plans:
            plan.reasons = importance_reasons(plan, world, self.settings.AUTO_POST_ENABLED)
        self.state.blocked = blocked
        return plans

    async def _explain_and_store(self, world: World, forecasts: dict, plans: list) -> list:
        rows = []
        for plan in plans:
            forecast = forecasts[(plan.station_id, plan.fuel_type)]
            try:
                explanation = self.explainer.explain(plan, forecast, world)
            except Exception:
                logger.exception("Explainer failed; using the template")
                explanation = self.fallback_explainer.explain(plan, forecast, world)
            important = bool(plan.reasons)
            rows.append({
                "tick": world.tick, "station_id": plan.station_id, "fuel_type": plan.fuel_type,
                "depot_id": plan.depot_id, "route_id": plan.route_id, "quantity": plan.quantity,
                "proposed_quantity": plan.quantity, "risk": plan.risk, "ticks_until_empty": plan.ticks_until_empty,
                "important": important, "decision_mode": "operator" if important else "auto",
                "reasons": plan.reasons, "explanation": explanation, "planner": plan.planner,
                "status": RecommendationStatus.PENDING_APPROVAL if important else RecommendationStatus.APPROVED,
            })
        if not rows:
            return []
        created = await self.recs.add_many(rows)
        await self.recs.commit()
        return created

    async def _post_approved(self, open_recs: list) -> dict[str, int]:
        counts = {"posted": 0, "refused": 0, "waiting": 0}
        approved = [r for r in open_recs if r.status == RecommendationStatus.APPROVED]
        for rec in approved:
            rec = await self.rec_service.post(rec, commit=False)
            counts[{"POSTED": "posted", "REFUSED": "refused"}.get(rec.status, "waiting")] += 1
        if approved:
            await self.recs.commit()
        return counts

    async def _expire_open(self, open_recs: list, tick: int, everything: bool = False) -> list:
        """Expires stale open recommendations; returns the ones still open."""
        keep, expired = [], False
        for rec in open_recs:
            if everything or tick < rec.tick or self._too_old(rec, tick):
                await self.recs.update(rec, {"status": RecommendationStatus.EXPIRED,
                                             "error_message": "simulator reset" if everything else "not answered in time"},
                                       commit=False)
                expired = True
            else:
                keep.append(rec)
        if expired:
            await self.recs.commit()
        return keep

    def _too_old(self, rec, tick: int) -> bool:
        """Old in simulator ticks AND in wall-clock time, so a fast simulator doesn't
        expire recommendations before a human can read them."""
        created = rec.created_at if rec.created_at.tzinfo else rec.created_at.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - created).total_seconds()
        return tick - rec.tick > self.settings.APPROVAL_TTL_TICKS and age_seconds > self.settings.APPROVAL_MIN_SECONDS

    async def _refresh_recs(self, stages: list[StageResult]) -> None:
        try:
            await self.rec_service.refresh_state()
        except Exception as exc:
            logger.exception("Could not load recommendations")
            stages.append(StageResult("monitor", "error", 0.0, f"recommendations unavailable: {exc}"[:300]))

    def _finish(self, stages: list[StageResult], started: float, tick: int | None) -> dict[str, Any]:
        state = self.state
        state.runs += 1
        state.stages = stages
        state.last_run = {"tick": tick, "at": time.time(), "duration_ms": round((time.perf_counter() - started) * 1000, 1)}
        state.publish()
        return {"ran": True, "tick": tick, "detail": None}


async def _async(fn: Callable, *args: Any) -> Any:
    return fn(*args)
