"""Decide stage: turn forecasts into shipment plans, and flag the important ones.

Baseline rules (no optimization):
- act on every station/fuel whose risk is `watch` or `urgent`, most urgent (lowest cover) first,
- skip stations that are not OPEN and station/fuels that already have an open recommendation,
- pick the fastest AVAILABLE route whose depot has the fuel (a backup route if the main one is cut),
- quantity = min(free tank space after incoming, route max, depot stock - reserve, depot dispatch left),
  rounded down to 100 L, and only if >= MIN_SHIPMENT_LITERS.
"""

import math
from dataclasses import dataclass
from typing import Any, Protocol

from app.pipeline.types import Blocked, Forecast, Plan, World

ACT_ON = ("urgent", "watch")


def floor_100(liters: float) -> float:
    return float(math.floor(liters / 100) * 100)


class Planner(Protocol):
    name: str

    def plan(self, world: World, forecasts: dict[tuple[str, str], Forecast],
             skip: set[tuple[str, str]]) -> tuple[list[Plan], list[Blocked]]: ...


class RulePlanner:
    name = "rules"

    def __init__(self, min_shipment: float, depot_reserve: float) -> None:
        self.min_shipment = min_shipment
        self.depot_reserve = depot_reserve

    def plan(self, world: World, forecasts: dict[tuple[str, str], Forecast],
             skip: set[tuple[str, str]]) -> tuple[list[Plan], list[Blocked]]:
        dispatch_left = {d: float(dep.get("dispatch_capacity_per_tick", 0)) - world.dispatch_used(d)
                         for d, dep in world.depots.items()}
        depot_stock = {(d, fuel): float(level) for d, dep in world.depots.items()
                       for fuel, level in dep.get("inventory", {}).items()}

        needs = sorted(
            (f for key, f in forecasts.items() if f.risk in ACT_ON and key not in skip),
            key=lambda f: f.cover_ticks if f.cover_ticks is not None else math.inf,
        )
        plans, blocked = [], []
        for f in needs:
            room = f.capacity - f.inventory - f.incoming
            if room < self.min_shipment:
                blocked.append(Blocked(f.station_id, f.fuel_type, f"tank has only {room:,.0f} L free after incoming"))
                continue
            routes = sorted(
                (r for r in world.routes_to(f.station_id)
                 if r.get("status") == "AVAILABLE" and r.get("source_depot_id") in world.depots),
                key=lambda r: (int(r["transit_ticks"]), -depot_stock.get((r["source_depot_id"], f.fuel_type), 0)),
            )
            if not routes:
                blocked.append(Blocked(f.station_id, f.fuel_type, "no available route"))
                continue
            chosen = None
            for route in routes:
                depot_id = route["source_depot_id"]
                stock = depot_stock.get((depot_id, f.fuel_type), 0) - self.depot_reserve
                qty = floor_100(min(room, float(route["max_shipment"]), stock, dispatch_left[depot_id]))
                if qty >= self.min_shipment:
                    chosen = (route, qty)
                    break
            if chosen is None:
                blocked.append(Blocked(f.station_id, f.fuel_type, "no depot with enough stock or dispatch capacity this tick"))
                continue
            route, qty = chosen
            depot_id = route["source_depot_id"]
            dispatch_left[depot_id] -= qty
            depot_stock[(depot_id, f.fuel_type)] -= qty
            plans.append(Plan(
                station_id=f.station_id, fuel_type=f.fuel_type, depot_id=depot_id, route_id=route["id"],
                quantity=qty, risk=f.risk, ticks_until_empty=f.ticks_until_empty, planner=self.name,
            ))
        return plans, blocked


def _event_touches(event: dict[str, Any], world: World, plan: Plan) -> bool:
    params = event.get("parameters") or {}
    station = world.stations.get(plan.station_id, {})
    filters = {
        "station_ids": plan.station_id, "region_ids": station.get("region_id"),
        "depot_ids": plan.depot_id, "route_ids": plan.route_id,
    }
    present = [k for k in filters if k in params]
    if not present:
        return True  # no filters -> applies to everything
    return any(not params[k] or filters[k] in params[k] for k in present)


def importance_reasons(plan: Plan, world: World, auto_post_enabled: bool) -> list[str]:
    """Why a plan needs the operator. Empty list -> it may be auto-posted."""
    reasons = []
    if plan.risk == "urgent":
        reasons.append("urgent: station may run dry before the truck arrives")
    route = world.routes[plan.route_id]
    fastest = min(int(r["transit_ticks"]) for r in world.routes_to(plan.station_id))
    if int(route["transit_ticks"]) > fastest:
        reasons.append(f"backup route ({route['transit_ticks']} ticks instead of {fastest})")
    if world.depots[plan.depot_id].get("status") != "OPEN":
        reasons.append(f"depot {plan.depot_id} is {world.depots[plan.depot_id].get('status')}")
    for event in world.events:
        if event.get("status") == "ACTIVE" and _event_touches(event, world, plan):
            reasons.append(f"active crisis: {event.get('type')} (event {event.get('id')})")
    if world.stale:
        reasons.append("simulator data is flagged stale (cautious mode)")
    if not auto_post_enabled:
        reasons.append("auto-post is disabled")
    return reasons


@dataclass
class Recheck:
    quantity: float  # liters to post now (0 when it can't be posted)
    code: str | None = None  # simulator-style code when it can't be posted
    reason: str = ""  # why it can't be posted, or why the quantity changed
    retry: bool = False  # can't post this tick, but may next tick (keep it APPROVED)


def recheck(world: World, *, station_id: str, fuel_type: str, depot_id: str, route_id: str, quantity: float,
            can_grow: bool, min_shipment: float, depot_reserve: float) -> Recheck:
    """Re-sizes an approved plan against the current world right before it is posted.

    The plan may be many ticks old (it waited for the operator, or is a retry), so the
    station may have drained, the depot emptied or the route been cut since. The quantity
    is re-fitted to the same limits the planner uses; `can_grow=False` (operator-edited
    quantity, or stale data) only lets it shrink.
    """
    station, depot, route = world.stations.get(station_id), world.depots.get(depot_id), world.routes.get(route_id)
    if station is None or depot is None or route is None:
        return Recheck(0.0, "NOT_FOUND", "station, depot or route no longer exists")
    if station.get("status") != "OPEN":
        return Recheck(0.0, "STATION_CLOSED", f"station is {station.get('status')}")
    if route.get("status") != "AVAILABLE":
        return Recheck(0.0, "ROUTE_DISRUPTED", f"route is {route.get('status')}")

    limits = {  # code the simulator would answer if we exceeded it -> liters allowed
        "DESTINATION_CAPACITY_EXCEEDED": float(station["capacity"].get(fuel_type, 0))
        - float(station["inventory"].get(fuel_type, 0)) - world.incoming(station_id, fuel_type),
        "ROUTE_CAPACITY_EXCEEDED": float(route["max_shipment"]),
        "INSUFFICIENT_INVENTORY": float(depot["inventory"].get(fuel_type, 0)) - depot_reserve,
        "DISPATCH_CAPACITY_EXCEEDED": float(depot.get("dispatch_capacity_per_tick", 0)) - world.dispatch_used(depot_id),
    }
    limit = floor_100(min(limits.values()))
    wanted = float(round(quantity))
    qty = limit if can_grow else min(wanted, limit)
    if qty >= min(min_shipment, wanted):
        reason = "" if qty == wanted else (
            f"refitted to the station's free space and depot limits now ({limits['DESTINATION_CAPACITY_EXCEEDED']:,.0f} L "
            f"free after incoming, {max(0.0, limits['INSUFFICIENT_INVENTORY']):,.0f} L in stock, "
            f"{max(0.0, limits['DISPATCH_CAPACITY_EXCEEDED']):,.0f} L dispatch left)")
        return Recheck(qty, reason=reason)
    code = min(limits, key=limits.get)
    reason = {
        "DESTINATION_CAPACITY_EXCEEDED": "station tank has too little free space after incoming shipments",
        "INSUFFICIENT_INVENTORY": "depot has too little stock",
        "DISPATCH_CAPACITY_EXCEEDED": "depot dispatch limit for this tick is used up",
    }.get(code, code)
    return Recheck(0.0, code, reason, retry=code == "DISPATCH_CAPACITY_EXCEEDED")
