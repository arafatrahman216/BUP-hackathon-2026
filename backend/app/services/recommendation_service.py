"""Operator approval (approve / edit / reject) and posting recommendations to the simulator."""

from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.recommendation import Recommendation, RecommendationStatus
from app.pipeline.state import PipelineState
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.simulator_repository import SimulatorError, SimulatorRejection, SimulatorRepository
from app.schemas.recommendation import RecommendationRead
from app.utils.logger import get_logger

logger = get_logger(__name__)


def idempotency_key(rec: Recommendation) -> str:
    """Deterministic per recommendation + quantity: a retry of the same post is safe,
    and an operator edit gets a new key instead of an IDEMPOTENCY_KEY_MISMATCH."""
    return f"bup-rec-{rec.id}-{rec.station_id}-{rec.fuel_type}-{int(rec.quantity)}".lower()


class RecommendationService:
    def __init__(self, repo: RecommendationRepository, sim: SimulatorRepository,
                 state: PipelineState, settings: Settings) -> None:
        self.repo = repo
        self.sim = sim
        self.state = state
        self.settings = settings

    async def get(self, rec_id: int) -> Recommendation:
        rec = await self.repo.get(rec_id)
        if rec is None:
            raise NotFoundError(f"Recommendation {rec_id} not found")
        return rec

    async def list(self, offset: int, limit: int, status: str | None) -> tuple[list[Recommendation], int]:
        return await self.repo.list(offset, limit, status)

    async def approve(self, rec_id: int, quantity: float | None, note: str | None) -> Recommendation:
        async with self.state.lock:
            rec = await self._pending(rec_id)
            changes: dict = {"status": RecommendationStatus.APPROVED, "decision_mode": "operator", "operator_note": note}
            if quantity is not None:
                route = self.state.world.routes.get(rec.route_id) if self.state.world else None
                if route and quantity > float(route["max_shipment"]):
                    raise BadRequestError(f"Quantity {quantity:g} exceeds the route maximum of {route['max_shipment']:g} L",
                                          code="QUANTITY_TOO_LARGE")
                changes["quantity"] = float(quantity)
            rec = await self.repo.update(rec, changes, commit=False)  # post() commits
            rec = await self.post(rec)
            await self.refresh_state()
        self.state.publish()
        return rec

    async def reject(self, rec_id: int, note: str | None) -> Recommendation:
        async with self.state.lock:
            rec = await self._pending(rec_id)
            rec = await self.repo.update(rec, {"status": RecommendationStatus.REJECTED, "decision_mode": "operator",
                                               "operator_note": note})
            await self.refresh_state()
        self.state.publish()
        return rec

    async def _pending(self, rec_id: int) -> Recommendation:
        rec = await self.get(rec_id)
        if rec.status != RecommendationStatus.PENDING_APPROVAL:
            raise ConflictError(f"Recommendation {rec_id} is {rec.status}, not waiting for approval",
                                code="NOT_PENDING_APPROVAL")
        return rec

    async def post(self, rec: Recommendation, *, commit: bool = True) -> Recommendation:
        """POST one APPROVED recommendation. Transient failures keep it APPROVED (retried
        on the next tick); a 4xx refusal marks it REFUSED with the simulator's code."""
        def update(data: dict):
            return self.repo.update(rec, data, commit=commit)

        if self.state.world is None or not self.state.acting:
            return await update({"error_message": "not posted: simulator data is stale or invalid; will retry"})
        key = idempotency_key(rec)
        body = {
            "idempotency_key": key, "source_depot_id": rec.depot_id, "destination_station_id": rec.station_id,
            "route_id": rec.route_id, "fuel_type": rec.fuel_type, "quantity": rec.quantity,
        }
        try:
            response = await self.sim.create_allocation(body)
        except SimulatorRejection as exc:
            logger.warning("Recommendation %s refused by simulator: %s", rec.id, exc)
            return await update({"status": RecommendationStatus.REFUSED, "idempotency_key": key,
                                                "error_code": exc.code, "error_message": exc.message})
        except SimulatorError as exc:
            logger.warning("Recommendation %s not posted (will retry): %s", rec.id, exc)
            return await update({"idempotency_key": key, "error_code": exc.code, "error_message": str(exc)})
        allocation = response.data
        logger.info("Posted recommendation %s -> allocation %s (%s %s %.0f L)", rec.id, allocation.get("id"),
                    rec.station_id, rec.fuel_type, rec.quantity)
        return await update({
            "status": RecommendationStatus.POSTED, "idempotency_key": key, "allocation_id": allocation.get("id"),
            "posted_tick": allocation.get("created_tick"), "error_code": None, "error_message": None,
        })

    async def refresh_state(self) -> None:
        """Reload the open and recent recommendations shown on the dashboard."""
        dump = lambda r: RecommendationRead.model_validate(r).model_dump(mode="json")  # noqa: E731
        self.state.recommendations = {
            "open": [dump(r) for r in await self.repo.list_open()],
            "recent": [dump(r) for r in await self.repo.recent(25)],
        }
