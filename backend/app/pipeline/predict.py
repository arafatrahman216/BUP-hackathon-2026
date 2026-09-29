"""Predict stage: demand rate per station/fuel and time until empty.

Baseline rule: rate = average demand over the last FORECAST_WINDOW_TICKS ticks of
demand history. No time-of-day pattern, no model; plug one in by writing another
class with the same `predict(world)` signature (see app/pipeline/__init__.py).
"""

from collections import defaultdict
from typing import Protocol

from app.pipeline.types import Forecast, World


class Predictor(Protocol):
    name: str

    def predict(self, world: World) -> dict[tuple[str, str], Forecast]: ...


def classify_risk(cover: float | None, lead: int | None, safety_ticks: int, urgent_margin: int) -> str:
    if cover is None:
        return "safe"
    lead = lead or 0
    if cover < lead + urgent_margin:
        return "urgent"
    if cover < lead + safety_ticks:
        return "watch"
    return "safe"


def lead_ticks(world: World, station_id: str) -> int | None:
    usable = [int(r["transit_ticks"]) for r in world.routes_to(station_id) if r.get("status") == "AVAILABLE"]
    return min(usable) if usable else None


def build_forecast(world: World, station_id: str, fuel: str, rate: float | None, *,
                   safety_ticks: int, urgent_margin: int, unmet: float = 0.0, source: str) -> Forecast:
    station = world.stations[station_id]
    inventory = float(station["inventory"].get(fuel, 0))
    incoming = world.incoming(station_id, fuel)
    lead = lead_ticks(world, station_id)
    if rate is None:
        tue = cover = None
        risk = "unknown"
    else:
        tue = inventory / rate if rate > 0 else None
        cover = (inventory + incoming) / rate if rate > 0 else None
        risk = classify_risk(cover, lead, safety_ticks, urgent_margin)
    if station.get("status") != "OPEN":
        risk = "outage"
    return Forecast(
        station_id=station_id, fuel_type=fuel, inventory=inventory,
        capacity=float(station["capacity"].get(fuel, 0)), rate_per_tick=rate, incoming=incoming,
        ticks_until_empty=tue, cover_ticks=cover, lead_ticks=lead, risk=risk,
        unmet_last_tick=unmet, source=source,
    )


class MovingAveragePredictor:
    name = "moving_average"

    def __init__(self, window_ticks: int, safety_ticks: int, urgent_margin: int) -> None:
        self.window = window_ticks
        self.safety_ticks = safety_ticks
        self.urgent_margin = urgent_margin

    def predict(self, world: World) -> dict[tuple[str, str], Forecast]:
        by_key: dict[tuple[str, str], dict[int, dict]] = defaultdict(dict)
        for row in world.history:
            by_key[(row["station_id"], row["fuel_type"])][int(row["tick"])] = row

        forecasts = {}
        for station_id in world.stations:
            for fuel in world.fuel_types:
                rows = by_key.get((station_id, fuel), {})
                recent = [rows[t] for t in sorted(rows, reverse=True)[: self.window]]
                rate = sum(float(r["demand_liters"]) for r in recent) / len(recent) if recent else None
                unmet = float(recent[0].get("unmet_liters") or 0) if recent else 0.0
                forecasts[(station_id, fuel)] = build_forecast(
                    world, station_id, fuel, rate, safety_ticks=self.safety_ticks,
                    urgent_margin=self.urgent_margin, unmet=unmet, source=self.name,
                )
        return forecasts


class LastKnownRatePredictor:
    """Fallback: reuse the last rates we computed (e.g. demand history unavailable)."""

    name = "last_known_rate"

    def __init__(self, rates: dict[tuple[str, str], float | None], safety_ticks: int, urgent_margin: int) -> None:
        self.rates = rates
        self.safety_ticks = safety_ticks
        self.urgent_margin = urgent_margin

    def predict(self, world: World) -> dict[tuple[str, str], Forecast]:
        return {
            (station_id, fuel): build_forecast(
                world, station_id, fuel, self.rates.get((station_id, fuel)),
                safety_ticks=self.safety_ticks, urgent_margin=self.urgent_margin, source=self.name,
            )
            for station_id in world.stations for fuel in world.fuel_types
        }
