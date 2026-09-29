"""Hard-coded backup data so the demo never shows an error (DEMO_MASK_ERRORS=true).

- `demo_world()`: the simulator's published baseline world (guide section 8) at tick 0. Used only when
  the simulator is unreachable and we have never read a real world. We never post allocations from it.
- `demo_forecasts()`: plain-arithmetic forecasts (known rates, or the published daily profile / 96),
  used when the predictor and its fallback both fail.

Every use is logged as "ERROR MASKED" by the caller.
"""

from typing import Any

from app.pipeline.demand_model import PROFILE_DAILY
from app.pipeline.predict import build_forecast
from app.pipeline.types import Forecast, World

DEFAULT_RATE = 100.0  # liters per tick if a station has no known profile


def _fuels(d: float, p: float, o: float) -> dict[str, float]:
    return {"DIESEL": d, "PETROL": p, "OCTANE": o}


def demo_world() -> World:
    depots = [
        {"id": "depot-gazipur", "name": "Gazipur Depot", "region_id": "region-dhaka", "status": "OPEN",
         "dispatch_capacity_per_tick": 12000, "capacity": _fuels(90000, 70000, 45000), "inventory": _fuels(60000, 45000, 26000)},
        {"id": "depot-patiya", "name": "Patiya Depot", "region_id": "region-chattogram", "status": "OPEN",
         "dispatch_capacity_per_tick": 11000, "capacity": _fuels(85000, 65000, 40000), "inventory": _fuels(55000, 42000, 24000)},
    ]
    stations = [
        ("station-mirpur", "Mirpur Fuel Station", "region-dhaka", "urban_high", _fuels(15000, 14000, 9000), _fuels(9000, 9000, 5000)),
        ("station-tongi", "Tongi Fuel Station", "region-dhaka", "industrial", _fuels(18000, 9000, 6000), _fuels(11000, 6000, 3500)),
        ("station-karnaphuli", "Karnaphuli Fuel Station", "region-chattogram", "highway", _fuels(14000, 15000, 9000), _fuels(8500, 9500, 5200)),
        ("station-coxsbazar", "Cox's Bazar Fuel Station", "region-chattogram", "regional", _fuels(12000, 12000, 7000), _fuels(7500, 7500, 4200)),
    ]
    routes = [
        ("route-gazipur-mirpur", "depot-gazipur", "station-mirpur", 2, 7000),
        ("route-gazipur-tongi", "depot-gazipur", "station-tongi", 2, 6500),
        ("route-patiya-karnaphuli", "depot-patiya", "station-karnaphuli", 2, 7000),
        ("route-patiya-coxsbazar", "depot-patiya", "station-coxsbazar", 3, 6000),
        ("route-gazipur-karnaphuli", "depot-gazipur", "station-karnaphuli", 4, 5000),
        ("route-patiya-mirpur", "depot-patiya", "station-mirpur", 4, 5000),
    ]
    return World(
        instance={"id": 1, "scenario_id": "demo-backup", "tick": 0, "sim_time": "2026-01-01T00:00:00+00:00",
                  "tick_minutes": 15, "status": "PAUSED"},
        depots={d["id"]: d for d in depots},
        stations={sid: {"id": sid, "name": name, "region_id": region, "status": "OPEN", "demand_profile": profile,
                        "demand_multiplier": 1.0, "capacity": cap, "inventory": inv}
                  for sid, name, region, profile, cap, inv in stations},
        routes={rid: {"id": rid, "source_depot_id": d, "destination_station_id": s, "transit_ticks": t,
                      "max_shipment": m, "status": "AVAILABLE"} for rid, d, s, t, m in routes},
        supply=[], events=[], allocations=[], history=[],
        metrics={"served_demand_liters": 0.0, "unmet_demand_liters": 0.0, "service_level": 1.0,
                 "allocation_liters": 0.0, "allocation_failures": 0},
        stale=True,
    )


def demo_rate(world: World, station_id: str, fuel: str) -> float:
    station = world.stations.get(station_id, {})
    daily = PROFILE_DAILY.get(station.get("demand_profile"), {}).get(fuel)
    ticks_per_day = max(1, 1440 // world.tick_minutes)
    return daily / ticks_per_day * float(station.get("demand_multiplier") or 1.0) if daily else DEFAULT_RATE


def demo_forecasts(world: World, safety_ticks: int, urgent_margin: int,
                   rates: dict[tuple[str, str], float | None] | None = None) -> dict[tuple[str, str], Forecast]:
    out: dict[tuple[str, str], Forecast] = {}
    for sid, station in world.stations.items():
        for fuel in station.get("capacity", {}):
            rate = (rates or {}).get((sid, fuel)) or demo_rate(world, sid, fuel)
            try:
                out[(sid, fuel)] = build_forecast(world, sid, fuel, rate, safety_ticks=safety_ticks,
                                                  urgent_margin=urgent_margin, source="backup")
            except Exception:  # malformed entity: skip it rather than fail the whole dashboard
                continue
    return out


def demo_dashboard(message: str = "Showing backup data") -> dict[str, Any]:
    """Minimal payload with the same keys as PipelineState.to_dashboard()."""
    world = demo_world()
    forecasts = demo_forecasts(world, 8, 2)
    return {
        "sim": {"connected": False, "link": "polling", "error": None, "stale": True, "data_age_seconds": None,
                "tick": 0, "sim_time": world.instance["sim_time"], "status": "PAUSED", "tick_minutes": 15,
                "demo": True, "note": message},
        "pipeline": {"acting": False, "runs": 0, "last_run": {}, "stages": [], "validation_issues": []},
        "alerts": [], "incidents": [], "outlook": {}, "blocked": [], "recommendations": {"open": [], "recent": []},
        "stations": [{**{k: s.get(k) for k in ("id", "name", "region_id", "status", "demand_profile", "demand_multiplier")},
                      "fuels": [forecasts[(sid, f)].to_dict() for f in s["capacity"] if (sid, f) in forecasts]}
                     for sid, s in world.stations.items()],
        "depots": [{**{k: d.get(k) for k in ("id", "name", "region_id", "status", "dispatch_capacity_per_tick")},
                    "dispatch_used": 0.0,
                    "fuels": [{"fuel_type": f, "inventory": d["inventory"][f], "capacity": d["capacity"][f]} for f in d["inventory"]]}
                   for d in world.depots.values()],
        "routes": list(world.routes.values()), "supply": [], "events": [], "allocations": [], "metrics": world.metrics,
    }
