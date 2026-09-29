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


@dataclass
class ReviewRules:
    """Stockout-risk triggers that send a shipment to the operator before the tank is nearly empty."""

    enabled: bool = True
    fill_fraction: float = 0.5  # tank at or below this share of capacity ...
    fill_horizon_ticks: float = 24.0  # ... and empties within this many ticks at the current rate
    stockout_prob: float = 0.3  # chance of running dry within the forecast horizon
    empty_margin_ticks: float = 4.0  # empties less than this many ticks after the fastest truck can land


def _risk_reasons(plan: Plan, f: Forecast | None, rules: ReviewRules) -> list[str]:
    """Why this station is at real risk of running dry: each reason carries the numbers behind it."""
    if not rules.enabled or f is None:
        return []
    reasons = []
    tue = f.ticks_until_empty if f.ticks_until_empty is not None else plan.ticks_until_empty
    rate = f.rate_per_tick or 0.0
    fill = f.inventory / f.capacity if f.capacity else None
    if fill is not None and fill <= rules.fill_fraction and tue is not None and tue <= rules.fill_horizon_ticks:
        reasons.append(f"tank at {fill:.0%} ({f.inventory:,.0f} / {f.capacity:,.0f} L), burning {rate:,.0f} L/tick: "
                       f"empty in ~{tue:.1f} ticks without a delivery")
    if f.p_stockout is not None and f.p_stockout >= rules.stockout_prob:
        reasons.append(f"stockout risk {f.p_stockout:.0%} within the forecast horizon "
                       f"(threshold {rules.stockout_prob:.0%})")
    if tue is not None and f.lead_ticks is not None and tue - f.lead_ticks < rules.empty_margin_ticks:
        margin = tue - f.lead_ticks
        reasons.append(f"fast drain: empty in ~{tue:.1f} ticks, fastest truck needs {f.lead_ticks} "
                       + (f"(only {margin:.1f} ticks to spare)" if margin >= 0 else f"(dry ~{-margin:.1f} ticks before it lands)"))
    unmet_after = plan.impact.get("unmet_after") if plan.impact else None
    if unmet_after:
        reasons.append(f"not enough: even with this shipment ~{unmet_after:,.0f} L stay unserved "
                       f"(vs ~{plan.impact.get('unmet_before', 0):,.0f} L without it)")
    return reasons


def importance_reasons(plan: Plan, world: World, auto_post_enabled: bool, *,
                       min_confidence: float = 0.0, rationing: bool = False,
                       urgent_depot_share: float = 0.5, forecast: Forecast | None = None,
                       review: ReviewRules | None = None) -> list[str]:
    """Why a plan needs the operator. Empty list -> it may be auto-posted.

    Trade-offs go to the operator (low confidence, over fair share, backup route, depot not OPEN, active
    crisis, stale data, draining a depot), and so does real stockout risk (`ReviewRules`): a tank half empty
    and emptying within the horizon, a high stockout probability, a thin margin over the truck's transit,
    or a shipment that still leaves demand unserved. An urgent shipment also needs the operator while there
    is still time to review it (the tank lasts at least the truck's trip); when the tank runs dry before the
    truck can arrive it is auto-posted: waiting would only add unserved demand. The dynamic approval
    deadline auto-approves an unanswered card once waiting starts to cost fuel.
    Rationing is approved at the policy level: shipments inside a station's fair-share budget
    stay automatic; only over-budget ones need the operator."""
    reasons = _risk_reasons(plan, forecast, review or ReviewRules())
    if plan.confidence is not None and plan.confidence < min_confidence:
        reasons.append(f"low forecast confidence ({plan.confidence:.2f})")
    if rationing and plan.over_budget:
        reasons.append("rationing: more than this station's fair share")
    route = world.routes[plan.route_id]
    if plan.risk == "urgent":
        transit = int(route["transit_ticks"])
        if plan.ticks_until_empty is not None and plan.ticks_until_empty >= transit:
            reasons.append(f"urgent: {plan.ticks_until_empty:.1f} ticks of fuel left and the truck needs {transit}, "
                           "so there is time to review")
        stock = float(world.depots[plan.depot_id]["inventory"].get(plan.fuel_type, 0))
        if stock > 0 and plan.quantity > urgent_depot_share * stock:
            reasons.append(f"urgent: takes {plan.quantity / stock:.0%} of {plan.depot_id}'s "
                           f"{plan.fuel_type} stock ({stock:,.0f} L)")
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
