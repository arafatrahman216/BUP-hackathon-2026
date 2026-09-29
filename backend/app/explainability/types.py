"""Data passed to metric functions.

Metrics read the same objects the tick pipeline works with: the `World` (everything read
from the simulator), the predict stage's `Forecast`s and the detect stage's `Alert`s, so an
explanation uses exactly the numbers the system decided with.
"""

from dataclasses import dataclass, field
from typing import Any

from app.pipeline.types import Alert, Blocked, Forecast, World


@dataclass
class Subject:
    """What the question is about. Any field may be empty (a general question)."""

    station_id: str | None = None
    fuel_type: str | None = None
    depot_id: str | None = None
    route_id: str | None = None
    action: dict[str, Any] | None = None  # the recommendation / allocation being explained

    @classmethod
    def build(cls, action: dict[str, Any] | None, **overrides: str | None) -> "Subject":
        """Fills the ids from the action (recommendation or allocation field names);
        explicit values win."""
        a = action or {}
        guessed = {
            "station_id": a.get("station_id") or a.get("destination_station_id"),
            "fuel_type": a.get("fuel_type"),
            "depot_id": a.get("depot_id") or a.get("source_depot_id"),
            "route_id": a.get("route_id"),
        }
        values = {k: overrides.get(k) or v for k, v in guessed.items()}
        if values["fuel_type"]:
            values["fuel_type"] = values["fuel_type"].upper()
        return cls(**values, action=action)

    def ids(self) -> dict[str, str]:
        return {k: v for k, v in {
            "station_id": self.station_id, "fuel_type": self.fuel_type,
            "depot_id": self.depot_id, "route_id": self.route_id,
        }.items() if v}


@dataclass
class Snapshot:
    """The pipeline's view of the world at one tick (cached, or read + computed live)."""

    world: World
    forecasts: dict[tuple[str, str], Forecast]
    alerts: list[Alert]
    blocked: list[Blocked] = field(default_factory=list)
    source: str = "pipeline_cache"  # pipeline_cache | live
    age_seconds: float | None = None
    outlook: dict[str, Any] = field(default_factory=dict)  # predictor: network fuel left, rationing, depot overflow
    planner_info: dict[str, Any] = field(default_factory=dict)  # last planner run: name, status, budgets
    incidents: list[dict[str, Any]] = field(default_factory=list)  # detector: grouped alerts


@dataclass
class MetricContext:
    """Input of every metric function."""

    snapshot: Snapshot
    subject: Subject
    params: dict[str, Any] = field(default_factory=dict)  # tuning knobs from profiles.json / the request
    rules: dict[str, Any] = field(default_factory=dict)  # pipeline settings (SAFETY_TICKS, ...)
    open_recommendations: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] | None = None  # longer demand history for the subject station, if read

    @property
    def world(self) -> World:
        return self.snapshot.world

    @property
    def tick(self) -> int:
        return self.world.tick

    def fuels(self, available: Any) -> list[str]:
        """The subject fuel if it is set and known, else every fuel in `available`."""
        fuel = self.subject.fuel_type
        return [fuel] if fuel and fuel in available else sorted(available)
