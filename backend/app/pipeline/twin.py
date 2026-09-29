"""Deterministic copy of the simulator (intelligence-plan §1, P2-P7).

Rolls the published rules forward H ticks from the current world:
- trucks already PENDING / IN_TRANSIT land at their expected arrival tick,
- scheduled supply ships land at depots; anything above depot capacity is wasted,
- fuel that doesn't fit in a station tank is lost (verified in our tests),
- during a station outage nothing is served, and demand is lost,
- extra shipments (a plan to test) leave the depot at their tick and fail if the road is cut then.

One engine gives time-until-empty, risk %, tank/depot overflow, and "with vs without" impact.
"""

import math
from dataclasses import dataclass, field
from typing import Any, Callable

from app.pipeline.demand_model import active_at, event_touches
from app.pipeline.types import World

DemandFn = Callable[[str, str, int], float]  # (station, fuel, k) -> liters at tick now+k


@dataclass
class Shipment:
    depart_k: int
    route_id: str
    fuel_type: str
    quantity: float


@dataclass
class StationPath:
    inventory: list[float] = field(default_factory=list)  # at the end of each tick
    mean_level: list[float] = field(default_factory=list)  # unfloored: inv + arrivals - demand (for risk %)
    demand: list[float] = field(default_factory=list)
    unmet: float = 0.0
    tank_overflow: float = 0.0
    stockout_k: int | None = None


@dataclass
class Projection:
    horizon: int
    stations: dict[tuple[str, str], StationPath]
    depot_overflow: dict[tuple[str, str], float]
    depot_overflow_k: dict[tuple[str, str], int | None]
    depot_inventory: dict[tuple[str, str], list[float]]
    failed_shipments: list[Shipment]

    @property
    def unmet(self) -> float:
        return sum(p.unmet for p in self.stations.values())

    @property
    def waste(self) -> float:
        return sum(p.tank_overflow for p in self.stations.values()) + sum(self.depot_overflow.values())


def route_open(world: World, route_id: str, tick: int) -> bool:
    """Is the road usable for a truck departing at `tick`? Uses current status and known events."""
    route = world.routes[route_id]
    disruptions = [e for e in world.events if e.get("type") == "route_disruption"
                   and event_touches(e, route_id=route_id) and e.get("status") != "RESOLVED"]
    if tick == world.tick and route.get("status") != "AVAILABLE":
        return False
    if any(active_at(e, tick) for e in disruptions):
        return False
    if route.get("status") != "AVAILABLE":  # cut now: open again only after its known end
        ends = [int(e["end_tick"]) for e in disruptions if e.get("status") == "ACTIVE" and e.get("end_tick") is not None]
        return bool(ends) and tick >= max(ends)
    return True


def station_open(world: World, station_id: str, tick: int) -> bool:
    station = world.stations[station_id]
    outages = [e for e in world.events if e.get("type") == "station_outage"
               and event_touches(e, station=station) and e.get("status") != "RESOLVED"]
    if tick == world.tick and station.get("status") != "OPEN":
        return False
    if any(active_at(e, tick) for e in outages):
        return False
    if station.get("status") != "OPEN":
        ends = [int(e["end_tick"]) for e in outages if e.get("status") == "ACTIVE" and e.get("end_tick") is not None]
        return bool(ends) and tick >= max(ends)
    return True


def fixed_arrivals(world: World) -> dict[tuple[str, str, int], float]:
    """Liters landing at (station, fuel, k) from shipments already created."""
    out: dict[tuple[str, str, int], float] = {}
    for a in world.allocations:
        if a.get("status") not in ("PENDING", "IN_TRANSIT"):
            continue
        route = world.routes.get(a.get("route_id"), {})
        eta = a.get("expected_arrival_tick")
        if eta is None:
            eta = int(a.get("created_tick") or world.tick) + int(route.get("transit_ticks") or 1)
        k = max(0, int(eta) - world.tick)
        key = (a["destination_station_id"], a["fuel_type"], k)
        out[key] = out.get(key, 0.0) + float(a.get("quantity") or 0)
    return out


def supply_arrivals(world: World) -> dict[tuple[str, str, int], float]:
    out: dict[tuple[str, str, int], float] = {}
    for s in world.supply:
        if s.get("status") == "ARRIVED":
            continue
        k = max(0, int(s.get("planned_tick") or world.tick) - world.tick)
        key = (s["depot_id"], s["fuel_type"], k)
        out[key] = out.get(key, 0.0) + float(s.get("quantity") or 0)
    return out


def project(world: World, demand: DemandFn, horizon: int, shipments: list[Shipment] | None = None,
            include_fixed: bool = True) -> Projection:
    fuels = world.fuel_types
    arrivals = fixed_arrivals(world) if include_fixed else {}
    supply = supply_arrivals(world)
    inv = {(s, f): float(st["inventory"].get(f, 0)) for s, st in world.stations.items() for f in fuels
           if f in st.get("capacity", {})}
    dep = {(d, f): float(dp["inventory"].get(f, 0)) for d, dp in world.depots.items() for f in fuels
           if f in dp.get("capacity", {})}
    paths = {key: StationPath() for key in inv}
    mean = dict(inv)
    depot_overflow = {key: 0.0 for key in dep}
    depot_overflow_k: dict[tuple[str, str], int | None] = {key: None for key in dep}
    depot_path: dict[tuple[str, str], list[float]] = {key: [] for key in dep}
    extra: dict[tuple[str, str, int], float] = {}
    failed = []
    by_k: dict[int, list[Shipment]] = {}
    for sh in shipments or []:
        by_k.setdefault(sh.depart_k, []).append(sh)

    for k in range(horizon):
        tick = world.tick + k
        # depots: supply lands (overflow wasted), then planned trucks leave
        for (d, f), level in dep.items():
            add = supply.get((d, f, k), 0.0)
            cap = float(world.depots[d]["capacity"].get(f, 0))
            if level + add > cap:
                depot_overflow[(d, f)] += level + add - cap
                depot_overflow_k[(d, f)] = depot_overflow_k[(d, f)] if depot_overflow_k[(d, f)] is not None else k
            dep[(d, f)] = min(cap, level + add)
        for sh in by_k.get(k, []):
            route = world.routes[sh.route_id]
            d, s = route["source_depot_id"], route["destination_station_id"]
            if not route_open(world, sh.route_id, tick) or not station_open(world, s, tick):
                failed.append(sh)
                continue
            qty = min(sh.quantity, dep.get((d, sh.fuel_type), 0.0))
            dep[(d, sh.fuel_type)] = dep.get((d, sh.fuel_type), 0.0) - qty
            akey = (s, sh.fuel_type, k + int(route["transit_ticks"]))
            extra[akey] = extra.get(akey, 0.0) + qty
        for key in dep:
            depot_path[key].append(dep[key])
        # stations: trucks land (overflow lost), then customers buy
        for (s, f), level in inv.items():
            p = paths[(s, f)]
            cap = float(world.stations[s]["capacity"].get(f, 0))
            land = arrivals.get((s, f, k), 0.0) + extra.get((s, f, k), 0.0)
            if level + land > cap:
                p.tank_overflow += level + land - cap
            level = min(cap, level + land)
            d_k = max(0.0, demand(s, f, k))
            p.demand.append(d_k)
            if station_open(world, s, tick):
                served = min(level, d_k)
                mean[(s, f)] += land - d_k
            else:
                served = 0.0
                mean[(s, f)] += land
            if served < d_k:
                p.unmet += d_k - served
                if p.stockout_k is None and station_open(world, s, tick):
                    p.stockout_k = k
            level -= served
            inv[(s, f)] = level
            p.inventory.append(level)
            p.mean_level.append(mean[(s, f)])
    return Projection(horizon, paths, depot_overflow, depot_overflow_k, depot_path, failed)


def p_stockout(path: StationPath, cv: float) -> float:
    """max over ticks of P(level < 0), noise independent per tick (normal approximation)."""
    var, best = 0.0, 0.0
    for m, d in zip(path.mean_level, path.demand):
        var += (cv * d) ** 2
        if var <= 0:
            continue
        z = m / math.sqrt(var)
        best = max(best, 0.5 * math.erfc(z / math.sqrt(2)))
    return round(best, 3)


def network_outlook(world: World, daily_rates: dict[tuple[str, str], float | None], trigger_days: float) -> dict[str, Any]:
    """P4 + P5: fuel left in the whole network, the day it runs out, and whether we ration."""
    ticks_per_day = max(1, 1440 // world.tick_minutes)
    in_transit: dict[str, float] = {}
    for a in world.allocations:
        if a.get("status") in ("PENDING", "IN_TRANSIT"):
            in_transit[a["fuel_type"]] = in_transit.get(a["fuel_type"], 0.0) + float(a.get("quantity") or 0)
    fuels = {}
    for f in world.fuel_types:
        stock = sum(float(d["inventory"].get(f, 0)) for d in world.depots.values()) \
            + sum(float(s["inventory"].get(f, 0)) for s in world.stations.values()) + in_transit.get(f, 0.0)
        remaining = sum(float(s.get("quantity") or 0) for s in world.supply
                        if s.get("fuel_type") == f and s.get("status") != "ARRIVED")
        per_tick = sum(r for (s, ff), r in daily_rates.items() if ff == f and r)
        days = (stock + remaining) / (per_tick * ticks_per_day) if per_tick else None
        fuels[f] = {
            "stock_liters": round(stock), "remaining_supply_liters": round(remaining),
            "demand_per_day": round(per_tick * ticks_per_day), "days_left": round(days, 2) if days is not None else None,
            "runs_out_at_tick": world.tick + int(days * ticks_per_day) if days is not None else None,
            "rationing": remaining == 0 or (days is not None and days < trigger_days),
        }
    return {"fuels": fuels, "rationing": any(v["rationing"] for v in fuels.values())}
