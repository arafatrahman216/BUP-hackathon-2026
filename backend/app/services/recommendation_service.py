"""Operator approval (approve / edit / reject) and posting recommendations to the simulator."""

from uuid import uuid4

from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.recommendation import Recommendation, RecommendationStatus
from app.pipeline.decide import recheck
from app.pipeline.state import PipelineState
from app.repositories.recommendation_repository import RecommendationRepository
from app.repositories.simulator_repository import SimulatorError, SimulatorRejection, SimulatorRepository
from app.schemas.recommendation import RecommendationRead
from app.utils.logger import get_logger

logger = get_logger(__name__)


def new_idempotency_key(station_id: str, fuel_type: str, quantity: float) -> str:
    """`bup-{token}-{station}-{fuel}-{liters}`. The random token is stored with the
    recommendation when it is created, so keys never repeat even if the database is
    reset while the simulator keeps its allocations (DB ids would repeat)."""
    return f"bup-{uuid4().hex[:12]}-{station_id}-{fuel_type}-{int(quantity)}".lower()


def idempotency_key(rec: Recommendation, quantity: float) -> str:
    """Same token, current quantity: a retry of the same post is safe, and a changed
    quantity (operator edit, re-fit) gets a new key instead of IDEMPOTENCY_KEY_MISMATCH."""
    if not rec.idempotency_key:
        return new_idempotency_key(rec.station_id, rec.fuel_type, quantity)
    return f"{rec.idempotency_key.rsplit('-', 1)[0]}-{int(quantity)}"


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
                changes["quantity"] = float(round(quantity))
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
        """POST one APPROVED recommendation, re-fitted to the current world first.

        - An earlier attempt that reached the simulator (answer lost) is found by its key -> POSTED.
        - Re-check fails -> REFUSED with the code the simulator would give, without calling it
          (dispatch limit used up: stays APPROVED and is retried next tick).
        - Transient failures keep it APPROVED (retried next tick); a 4xx refusal -> REFUSED.
        """
        def update(data: dict):
            return self.repo.update(rec, data, commit=commit)

        world = self.state.world
        if world is None or not self.state.acting:
            return await update({"error_message": "not posted: simulator data is stale or invalid; will retry"})
        if rec.idempotency_key:
            earlier = next((a for a in world.allocations if a.get("idempotency_key") == rec.idempotency_key), None)
            if earlier:
                return await self._posted(rec, earlier, update)

        s = self.settings
        check = recheck(
            world, station_id=rec.station_id, fuel_type=rec.fuel_type, depot_id=rec.depot_id, route_id=rec.route_id,
            quantity=rec.quantity, min_shipment=s.MIN_SHIPMENT_LITERS, depot_reserve=s.DEPOT_RESERVE_LITERS,
            # operator-edited quantities and stale data may only shrink
            can_grow=not self.state.cautious and (rec.decision_mode == "auto" or rec.quantity == rec.proposed_quantity),
        )
        if check.code:
            logger.info("Recommendation %s not posted after re-check: %s", rec.id, check.reason)
            if check.retry:
                return await update({"error_code": check.code, "error_message": f"waiting: {check.reason}; will retry"})
            return await update({"status": RecommendationStatus.REFUSED, "error_code": check.code,
                                 "error_message": f"checked before posting: {check.reason}"})

        changes: dict = {"idempotency_key": idempotency_key(rec, check.quantity)}
        if check.quantity != rec.quantity:
            changes["quantity"] = check.quantity
            changes["explanation"] = (f"{rec.explanation} Resized from {rec.quantity:,.0f} to {check.quantity:,.0f} L "
                                      f"at tick {world.tick}: {check.reason}.").strip()
        body = {
            "idempotency_key": changes["idempotency_key"], "source_depot_id": rec.depot_id,
            "destination_station_id": rec.station_id, "route_id": rec.route_id, "fuel_type": rec.fuel_type,
            "quantity": check.quantity,
        }
        try:
            response = await self.sim.create_allocation(body)
        except SimulatorRejection as exc:
            if exc.code == "DISPATCH_CAPACITY_EXCEEDED":  # per-tick limit: frees up next tick
                logger.info("Recommendation %s waits for dispatch capacity: %s", rec.id, exc)
                return await update({**changes, "error_code": exc.code, "error_message": f"waiting: {exc.message}"})
            logger.warning("Recommendation %s refused by simulator: %s", rec.id, exc)
            return await update({**changes, "status": RecommendationStatus.REFUSED,
                                 "error_code": exc.code, "error_message": exc.message})
        except SimulatorError as exc:
            logger.warning("Recommendation %s not posted (will retry): %s", rec.id, exc)
            return await update({**changes, "error_code": exc.code, "error_message": str(exc)})
        return await self._posted(rec, response.data, lambda data: update({**changes, **data}))

    async def _posted(self, rec: Recommendation, allocation: dict, update) -> Recommendation:
        logger.info("Posted recommendation %s -> allocation %s (%s %s %.0f L)", rec.id, allocation.get("id"),
                    rec.station_id, rec.fuel_type, float(allocation.get("quantity") or rec.quantity))
        self._remember(allocation)
        return await update({
            "status": RecommendationStatus.POSTED, "idempotency_key": allocation.get("idempotency_key"),
            "quantity": float(allocation.get("quantity") or rec.quantity), "allocation_id": allocation.get("id"),
            "posted_tick": allocation.get("created_tick"), "error_code": None, "error_message": None,
        })

    def _remember(self, allocation: dict) -> None:
        """Adds our new allocation to the cached world (the simulator already deducted the
        depot stock), so later re-checks this tick see the incoming fuel and dispatch used."""
        world = self.state.world
        if world is None or any(a.get("id") == allocation.get("id") for a in world.allocations):
            return
        world.allocations.insert(0, allocation)
        depot, fuel = world.depots.get(allocation.get("source_depot_id")), allocation.get("fuel_type")
        if depot and fuel in depot.get("inventory", {}):
            depot["inventory"][fuel] = float(depot["inventory"][fuel]) - float(allocation.get("quantity") or 0)

    async def refresh_state(self) -> None:
        """Reload the open and recent recommendations shown on the dashboard."""
        dump = lambda r: RecommendationRead.model_validate(r).model_dump(mode="json")  # noqa: E731
        self.state.recommendations = {
            "open": [dump(r) for r in await self.repo.list_open()],
            "recent": [dump(r) for r in await self.repo.recent(25)],
        }
