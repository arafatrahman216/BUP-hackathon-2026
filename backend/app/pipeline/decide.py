"""Decide stage: turn forecasts into shipment plans, and flag the important ones.

Baseline rules (no optimization):
- act on every station/fuel whose risk is `watch` or `urgent`, most urgent (lowest cover) first,
- skip stations that are not OPEN and station/fuels that already have an open recommendation,
- pick the fastest AVAILABLE route whose depot has the fuel (a backup route if the main one is cut),
- quantity = min(free tank space after incoming, route max, depot stock - reserve, depot dispatch left),
  rounded down to 100 L, and only if >= MIN_SHIPMENT_LITERS.
"""

import math
from typing import Any, Protocol

from app.pipeline.types import Blocked, Forecast, Plan, World

ACT_ON = ("urgent", "watch")


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
                qty = math.floor(min(room, float(route["max_shipment"]), stock, dispatch_left[depot_id]) / 100) * 100
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
                quantity=float(qty), risk=f.risk, ticks_until_empty=f.ticks_until_empty, planner=self.name,
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


def importance_reasons(plan: Plan, world: World, auto_post_enabled: bool, *,
                       min_confidence: float = 0.0, rationing: bool = False) -> list[str]:
    """Why a plan needs the operator. Empty list -> it may be auto-posted.

    Rationing is approved at the policy level: shipments inside a station's fair-share budget
    stay automatic; only over-budget ones need the operator."""
    reasons = []
    if plan.confidence is not None and plan.confidence < min_confidence:
        reasons.append(f"low forecast confidence ({plan.confidence:.2f})")
    if rationing and plan.over_budget:
        reasons.append("rationing: more than this station's fair share")
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
    if not auto_post_enabled:
        reasons.append("auto-post is disabled")
    return reasons
