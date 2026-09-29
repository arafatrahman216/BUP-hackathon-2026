"""Predict stage: demand rate per station/fuel and time until empty.

Baseline rule: rate = average demand over the last FORECAST_WINDOW_TICKS ticks of
demand history. No time-of-day pattern, no model; plug one in by writing another
class with the same `predict(world)` signature (see app/pipeline/__init__.py).
"""

import math
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


class StructuralPredictor:
    """P1-P8: structural demand model + deterministic simulator copy.

    Needs `model.ingest(world)` to have run this tick (the Detector does it before predict).
    Also leaves `self.outlook` (network fuel left / rationing, depot overflow) for the dashboard
    and the planner.
    """

    name = "structural"

    def __init__(self, model, horizon: int, safety_ticks: int, urgent_margin: int, trigger_days: float) -> None:
        from app.pipeline import twin  # local import: twin imports types only

        self.twin = twin
        self.model = model
        self.horizon = horizon
        self.safety_ticks = safety_ticks
        self.urgent_margin = urgent_margin
        self.trigger_days = trigger_days
        self.outlook: dict = {}

    def predict(self, world: World) -> dict[tuple[str, str], Forecast]:
        H, twin, model = self.horizon, self.twin, self.model
        paths = {(s, f): model.path(world, s, f, H) for s in world.stations for f in world.fuel_types
                 if f in world.stations[s].get("capacity", {})}
        if any(p is None for p in paths.values()):
            raise ValueError("no demand prior or history for some station/fuel")

        projection = twin.project(world, lambda s, f, k: paths[(s, f)][k], H)
        crisis = {s for s, st in world.stations.items()
                  if any(e.get("status") == "ACTIVE" and e.get("type") in ("demand_spike", "station_outage")
                         and self._touches(e, st) for e in world.events)}
        forecasts = {}
        for (s, f), demand in paths.items():
            station = world.stations[s]
            p = projection.stations[(s, f)]
            inventory = float(station["inventory"].get(f, 0))
            capacity = float(station["capacity"].get(f, 0))
            incoming = world.incoming(s, f)
            rate_now = demand[0]
            avg = sum(demand) / len(demand) if demand else 0.0
            lead = lead_ticks(world, s)
            if p.stockout_k is not None:
                cover = float(p.stockout_k)
            else:  # extrapolate past the horizon with the average rate
                cover = H + (p.inventory[-1] / avg if avg > 0 else math.inf)
            cover = None if math.isinf(cover) else cover
            risk = "outage" if station.get("status") != "OPEN" else classify_risk(cover, lead, self.safety_ticks, self.urgent_margin)
            cv = model.cv(s, f)
            wape = model.wape(s, f)
            confidence = 1.0 - min(1.0, wape if wape is not None else cv)
            if model.observations(s, f) < 24:
                confidence *= 0.8
            if world.stale:
                confidence *= 0.5
            if s in crisis:
                confidence *= 0.8
            order_by = refill_from = None
            if lead is not None and p.stockout_k is not None:
                order_by = world.tick + max(0, p.stockout_k - lead)
            fastest = min((r for r in world.routes_to(s) if r.get("status") == "AVAILABLE"),
                          key=lambda r: int(r["transit_ticks"]), default=None)
            if fastest is not None:
                L, truck = int(fastest["transit_ticks"]), float(fastest["max_shipment"])
                for k in range(0, H - L):
                    level_at_arrival = p.inventory[k + L - 1] if k + L - 1 >= 0 else inventory
                    if capacity - level_at_arrival >= min(truck, capacity * 0.5):
                        refill_from = world.tick + k
                        break
            history_rows = [r for r in world.history if r.get("station_id") == s and r.get("fuel_type") == f]
            last = max(history_rows, key=lambda r: r["tick"], default=None)
            forecasts[(s, f)] = Forecast(
                station_id=s, fuel_type=f, inventory=inventory, capacity=capacity, rate_per_tick=round(rate_now, 2),
                incoming=incoming, ticks_until_empty=cover, cover_ticks=cover, lead_ticks=lead, risk=risk,
                unmet_last_tick=float(last.get("unmet_liters") or 0) if last else 0.0, source=self.name,
                naive_ticks_until_empty=(inventory + incoming) / rate_now if rate_now > 0 else None,
                p_stockout=twin.p_stockout(p, cv), unmet_horizon=round(p.unmet, 1),
                tank_overflow_horizon=round(p.tank_overflow, 1), order_by_tick=order_by, refill_from_tick=refill_from,
                confidence=round(confidence, 2), cv=round(cv, 3),
                daily_rate_per_tick=model.daily_rate(world, s, f), demand_path=[round(x, 1) for x in demand],
            )
        daily = {k: f.daily_rate_per_tick for k, f in forecasts.items()}
        self.outlook = twin.network_outlook(world, daily, self.trigger_days)
        self.outlook["depots"] = [
            {"depot_id": d, "fuel_type": f, "inventory": round(projection.depot_inventory[(d, f)][0]) if projection.depot_inventory[(d, f)] else None,
             "overflow_liters": round(v), "overflow_in_ticks": projection.depot_overflow_k[(d, f)]}
            for (d, f), v in projection.depot_overflow.items()
        ]
        self.outlook["do_nothing"] = {"unmet_liters": round(projection.unmet), "waste_liters": round(projection.waste),
                                      "horizon_ticks": H}
        return forecasts

    @staticmethod
    def _touches(event, station) -> bool:
        from app.pipeline.demand_model import event_touches

        return event_touches(event, station=station)
