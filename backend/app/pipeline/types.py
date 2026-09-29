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


@dataclass
class Blocked:
    """A station/fuel that needs fuel but no shipment could be planned."""

    station_id: str
    fuel_type: str
    reason: str
