"""Data passed between pipeline stages. Simulator payloads stay as plain dicts
(as returned by the API); everything we derive is a dataclass."""

from dataclasses import asdict, dataclass, field
from typing import Any

ACTIVE_ALLOCATION = ("PENDING", "IN_TRANSIT")


@dataclass
class World:
    """Everything read from the simulator for one tick."""

    instance: dict[str, Any]
    depots: dict[str, dict[str, Any]]
    stations: dict[str, dict[str, Any]]
    routes: dict[str, dict[str, Any]]
    supply: list[dict[str, Any]]
    events: list[dict[str, Any]]
    allocations: list[dict[str, Any]]
    history: list[dict[str, Any]]
    metrics: dict[str, Any]
    stale: bool = False

    @property
    def tick(self) -> int:
        return int(self.instance.get("tick", 0))

    @property
    def tick_minutes(self) -> int:
        return int(self.instance.get("tick_minutes") or 15)

    @property
    def fuel_types(self) -> list[str]:
        fuels: set[str] = set()
        for station in self.stations.values():
            fuels.update(station.get("capacity", {}))
        return sorted(fuels)

    def routes_to(self, station_id: str) -> list[dict[str, Any]]:
        return [r for r in self.routes.values() if r.get("destination_station_id") == station_id]

    def incoming(self, station_id: str, fuel: str) -> float:
        return sum(
            float(a.get("quantity", 0)) for a in self.allocations
            if a.get("destination_station_id") == station_id and a.get("fuel_type") == fuel
            and a.get("status") in ACTIVE_ALLOCATION
        )

    def dispatch_used(self, depot_id: str) -> float:
        """Liters already committed from this depot on the current tick (dispatch limit rule)."""
        return sum(
            float(a.get("quantity", 0)) for a in self.allocations
            if a.get("source_depot_id") == depot_id
            and (a.get("status") == "PENDING" or (a.get("status") == "IN_TRANSIT" and a.get("created_tick") == self.tick))
        )


@dataclass
class Alert:
    level: str  # info | warning | critical
    code: str
    message: str
    entity_id: str | None = None
    explained_by: str | None = None  # "event 3 (demand_spike)" when a known crisis explains it
    since_tick: int | None = None  # first tick this alert was active (set by the Detector)
    region_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Forecast:
    station_id: str
    fuel_type: str
    inventory: float
    capacity: float
    rate_per_tick: float | None  # expected liters consumed per tick
    incoming: float  # PENDING + IN_TRANSIT liters heading here
    ticks_until_empty: float | None  # inventory / rate (None = never / unknown)
    cover_ticks: float | None  # (inventory + incoming) / rate
    lead_ticks: int | None  # transit of the fastest usable route
    risk: str  # safe | watch | urgent | outage | unknown
    unmet_last_tick: float = 0.0
    source: str = "moving_average"
    # --- structural predictor + simulator copy (None/empty for the moving-average baseline) ---
    naive_ticks_until_empty: float | None = None  # straight line: (inventory + incoming) / current rate
    p_stockout: float | None = None  # chance of running dry within the horizon (normal approximation)
    unmet_horizon: float | None = None  # liters we expect to lose within the horizon if we do nothing
    tank_overflow_horizon: float | None = None  # liters lost because incoming trucks don't fit
    order_by_tick: int | None = None  # latest tick to create a shipment that lands before empty
    refill_from_tick: int | None = None  # earliest tick a full truck fits on arrival
    confidence: float | None = None  # 0..1
    cv: float | None = None  # relative forecast error per tick
    daily_rate_per_tick: float | None = None  # time-of-day averaged rate x current multiplier
    demand_path: list[float] = field(default_factory=list)  # forecast liters for the next H ticks

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    """A proposed shipment, before it becomes a Recommendation row."""

    station_id: str
    fuel_type: str
    depot_id: str
    route_id: str
    quantity: float
    risk: str
    ticks_until_empty: float | None
    reasons: list[str] = field(default_factory=list)  # why it is "important" (empty -> auto)
    planner: str = "rules"
    confidence: float | None = None
    over_budget: bool = False  # rationing: more than this station's fair share
    impact: dict[str, Any] = field(default_factory=dict)  # with/without numbers from the simulator copy


@dataclass
class Blocked:
    """A station/fuel that needs fuel but no shipment could be planned."""

    station_id: str
    fuel_type: str
    reason: str
