"""Metric registry: each metric turns the pipeline's view of the world into one JSON block
of the LLM context.

Add a metric:

    @metric("my_metric", description="What the LLM learns from it")
    def my_metric(ctx: MetricContext) -> Any:
        return {...}          # JSON-serializable; return None to leave it out (not applicable)

then list it in a profile in `profiles.json`. Metrics are pure (no I/O). Detection and
prediction are NOT recomputed here: `forecast`, `alerts` and `station_ranking` expose the
pipeline's own predict/detect output, so the explanation matches what the system did.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.explainability.types import MetricContext
from app.pipeline.types import ACTIVE_ALLOCATION, Forecast

MetricFn = Callable[[MetricContext], Any]


@dataclass(frozen=True)
class MetricSpec:
    name: str
    description: str
    fn: MetricFn


METRICS: dict[str, MetricSpec] = {}


def metric(name: str, *, description: str = "") -> Callable[[MetricFn], MetricFn]:
    def register(fn: MetricFn) -> MetricFn:
        METRICS[name] = MetricSpec(name, description or (fn.__doc__ or "").strip(), fn)
        return fn
    return register


def _r(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(float(value), digits)


def _forecast(f: Forecast) -> dict[str, Any]:
    return {
        "station_id": f.station_id, "fuel_type": f.fuel_type, "risk": f.risk,
        "inventory_l": _r(f.inventory), "capacity_l": _r(f.capacity), "free_space_l": _r(f.capacity - f.inventory - f.incoming),
        "incoming_l": _r(f.incoming), "rate_l_per_tick": _r(f.rate_per_tick),
        "ticks_until_empty": _r(f.ticks_until_empty), "cover_ticks": _r(f.cover_ticks),
        "lead_ticks": f.lead_ticks, "margin_ticks": _r(f.cover_ticks - f.lead_ticks)
        if f.cover_ticks is not None and f.lead_ticks is not None else None,
        "unmet_last_tick_l": _r(f.unmet_last_tick), "predictor": f.source,
        # structural predictor (simulator copy); None for the moving-average baseline
        "p_stockout": f.p_stockout, "confidence": f.confidence,
        "expected_unmet_next_horizon_l": _r(f.unmet_horizon), "tank_overflow_next_horizon_l": _r(f.tank_overflow_horizon),
        "order_by_tick": f.order_by_tick, "refill_from_tick": f.refill_from_tick,
        "ticks_until_empty_at_current_rate": _r(f.naive_ticks_until_empty),
        "daily_avg_rate_l_per_tick": _r(f.daily_rate_per_tick),
        "demand_next_ticks_l": [_r(x) for x in f.demand_path[:8]],
    }


def _subject_station(ctx: MetricContext) -> dict[str, Any] | None:
    return ctx.world.stations.get(ctx.subject.station_id or "")


# ---------- the action and the clock ----------

@metric("clock", description="Current tick, simulated time, simulator status and where the data came from")
def clock(ctx: MetricContext) -> Any:
    i = ctx.world.instance
    return {**{k: i.get(k) for k in ("tick", "sim_time", "tick_minutes", "status")},
            "data_source": ctx.snapshot.source, "data_age_seconds": _r(ctx.snapshot.age_seconds)}


@metric("action", description="The action being explained (recommendation or allocation), as stored")
def action(ctx: MetricContext) -> Any:
    return ctx.subject.action


@metric("allocation", description="What happened to the shipment the action created: status, departure, arrival, failure")
def allocation(ctx: MetricContext) -> Any:
    a = ctx.subject.action or {}
    alloc_id = a.get("allocation_id") if a.get("kind") == "recommendation" else a.get("id") if a.get("kind") == "allocation" else None
    if alloc_id is None:
        return None
    found = next((x for x in ctx.world.allocations if x.get("id") == alloc_id), None)
    if found is None:
        return {"id": alloc_id, "note": "not in the simulator's current allocation list"}
    keys = ("id", "status", "quantity", "created_tick", "departure_tick", "expected_arrival_tick",
            "actual_arrival_tick", "failure_reason")
    out = {k: found.get(k) for k in keys}
    if found.get("actual_arrival_tick") is not None and found.get("expected_arrival_tick") is not None:
        out["arrival_delay_ticks"] = found["actual_arrival_tick"] - found["expected_arrival_tick"]
    return out


# ---------- predict / detect output (the pipeline's own numbers) ----------

@metric("forecast", description="Predict stage output for the station: rate, cover, lead time, margin, risk")
def forecast(ctx: MetricContext) -> Any:
    st = _subject_station(ctx)
    if st is None:
        return None
    out = {f: _forecast(ctx.snapshot.forecasts[(st["id"], f)]) for f in ctx.fuels(st.get("capacity") or {})
           if (st["id"], f) in ctx.snapshot.forecasts}
    for value in out.values():
        del value["station_id"], value["fuel_type"]
    return out or None


@metric("risk_rules", description="The rules that turn a forecast into risk / a shipment / operator review, "
                                  "with this station's thresholds and verdict")
def risk_rules(ctx: MetricContext) -> Any:
    r = ctx.rules
    structural = r.get("PREDICTOR") == "structural"
    out: dict[str, Any] = {
        "predictor": r.get("PREDICTOR"), "planner": r.get("PLANNER"),
        "risk": (f"urgent if cover < lead + {r.get('URGENT_MARGIN_TICKS')} ticks; watch (reorder) if cover < lead + "
                 f"{r.get('SAFETY_TICKS')} ticks; otherwise safe. "
                 + (f"cover = ticks until empty on the forecast demand path (time-of-day demand model + simulator copy, "
                    f"{r.get('FORECAST_HORIZON_TICKS')}-tick horizon), counting incoming trucks"
                    if structural else
                    f"cover = (inventory + incoming) / rate, rate = mean demand of the last {r.get('FORECAST_WINDOW_TICKS')} ticks")),
        "shipment": ((f"optimizer: plans shipments over the {r.get('FORECAST_HORIZON_TICKS')}-tick horizon to minimise "
                      f"unserved demand within route max, depot stock, dispatch limits and tank room; the rule planner is the fallback"
                      if r.get("PLANNER") == "optimizer" else
                      f"only watch/urgent get a shipment: fastest AVAILABLE route; quantity = min(free space after incoming, "
                      f"route max, depot stock - {r.get('DEPOT_RESERVE_LITERS')} L reserve, depot dispatch left this tick), "
                      f"floored to 100 L, at least {r.get('MIN_SHIPMENT_LITERS')} L")
                     + "; skipped if one is already open for the station/fuel"),
        "operator_review": (f"forecast confidence below {r.get('MIN_CONFIDENCE_AUTO')}, rationing over a station's fair share, "
                            "backup route, depot not OPEN, an ACTIVE crisis touching the station/region/"
                            "depot/route, stale data" + ("" if r.get("AUTO_POST_ENABLED", True) else ", or auto-post disabled (it is)")
                            + ", an urgent shipment while the tank still lasts the truck's trip (time to review), or an "
                            f"urgent shipment taking more than {r.get('URGENT_REVIEW_DEPOT_SHARE', 0.5):.0%} of the depot's "
                            "stock -> PENDING_APPROVAL; otherwise auto-posted. An urgent shipment to a tank that runs dry "
                            "before the truck can arrive is auto-posted at once, because waiting would only add unserved demand"),
        "rationing": f"a fuel is rationed when the network has less than {r.get('RATIONING_TRIGGER_DAYS')} days of it left",
        "expiry": f"open recommendations expire after {r.get('APPROVAL_TTL_TICKS')} ticks and {r.get('APPROVAL_MIN_SECONDS')} s",
    }
    st = _subject_station(ctx)
    if st is not None:
        verdicts = {}
        for fuel in ctx.fuels(st.get("capacity") or {}):
            f = ctx.snapshot.forecasts.get((st["id"], fuel))
            if f is None:
                continue
            lead = f.lead_ticks or 0
            verdicts[fuel] = {
                "cover_ticks": _r(f.cover_ticks), "urgent_below_cover": lead + int(r.get("URGENT_MARGIN_TICKS", 0)),
                "watch_below_cover": lead + int(r.get("SAFETY_TICKS", 0)), "risk": f.risk,
                "gets_shipment": f.risk in ("watch", "urgent"),
            }
        out["this_station"] = verdicts
    return out


@metric("alerts", description="Detect stage alerts (and blocked needs) for the subject, or all of them")
def alerts(ctx: MetricContext) -> Any:
    ids = {v for k, v in ctx.subject.ids().items() if k != "fuel_type"}
    rows = [a.to_dict() for a in ctx.snapshot.alerts if not ids or a.entity_id in ids or a.entity_id is None]
    rows += [{"level": "warning", "code": "BLOCKED", "message": f"{b.station_id} {b.fuel_type}: {b.reason}",
              "entity_id": b.station_id} for b in ctx.snapshot.blocked
             if not ids or b.station_id == ctx.subject.station_id]
    return rows


@metric("station_ranking", description="Every station/fuel sorted by cover (closest to running dry first)")
def station_ranking(ctx: MetricContext) -> Any:
    rows = sorted(ctx.snapshot.forecasts.values(),
                  key=lambda f: (f.cover_ticks is None, f.cover_ticks if f.cover_ticks is not None else 0))
    keys = ("station_id", "fuel_type", "risk", "inventory_l", "incoming_l", "rate_l_per_tick",
            "ticks_until_empty", "cover_ticks", "lead_ticks", "margin_ticks")
    return [{k: _forecast(f)[k] for k in keys} for f in rows[: int(ctx.params.get("ranking_size", 10))]]


# ---------- station ----------

@metric("station", description="Station status, demand profile and fuel levels")
def station(ctx: MetricContext) -> Any:
    st = _subject_station(ctx)
    if st is None:
        return None
    capacity, inventory = st.get("capacity") or {}, st.get("inventory") or {}
    return {
        **{k: st.get(k) for k in ("id", "name", "region_id", "status", "demand_profile", "demand_multiplier")},
        "fuels": {
            fuel: {"inventory_l": _r(inventory.get(fuel, 0)), "capacity_l": _r(capacity[fuel]),
                   "fill_pct": _r(100 * float(inventory.get(fuel, 0)) / float(capacity[fuel])) if capacity[fuel] else None}
            for fuel in ctx.fuels(capacity)
        },
    }


def _trend_run_out(inventory: float, latest: float, slope: float, limit: int = 500) -> float | None:
    """Ticks until empty if demand keeps changing by `slope` L per tick (None if it never empties)."""
    left, demand = inventory, latest
    for t in range(limit):
        demand = max(0.0, demand + slope)
        if demand >= left:
            return t + (left / demand if demand else 0)
        left -= demand
    return None


@metric("demand", description="Recent demand/served/unmet per tick, latest value, trend and a trend-based run-out")
def demand(ctx: MetricContext) -> Any:
    st = _subject_station(ctx)
    if st is None:
        return None
    source = ctx.history if ctx.history is not None else ctx.world.history
    out = {}
    for fuel in ctx.fuels(st.get("capacity") or {}):
        rows = sorted((r for r in source if r.get("station_id") == st["id"] and r.get("fuel_type") == fuel),
                      key=lambda r: r.get("tick", 0))[-int(ctx.params.get("history_ticks", 16)):]
        if not rows:
            continue
        values = [float(r.get("demand_liters") or 0) for r in rows]
        n = len(values)
        mean_x, mean_y = (n - 1) / 2, sum(values) / n
        var = sum((i - mean_x) ** 2 for i in range(n))
        slope = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values)) / var if var else 0.0
        inventory = float((st.get("inventory") or {}).get(fuel, 0)) + ctx.world.incoming(st["id"], fuel)
        out[fuel] = {
            "ticks": [rows[0].get("tick"), rows[-1].get("tick")],
            "latest_l": _r(values[-1]), "mean_l": _r(mean_y), "max_l": _r(max(values)),
            "slope_l_per_tick": _r(slope, 2),
            "unmet_total_l": _r(sum(float(r.get("unmet_liters") or 0) for r in rows)),
            "cover_ticks_if_trend_continues": _r(_trend_run_out(inventory, values[-1], slope))
            if abs(slope) >= float(ctx.params.get("trend_min_slope", 0.5)) else None,
            "series": [{"tick": r.get("tick"), "demand": _r(r.get("demand_liters")),
                        "served": _r(r.get("served_liters")), "unmet": _r(r.get("unmet_liters"))} for r in rows],
        }
    return out or None


@metric("incoming_shipments", description="PENDING / IN_TRANSIT shipments heading to the station")
def incoming_shipments(ctx: MetricContext) -> Any:
    if not ctx.subject.station_id:
        return None
    keys = ("id", "fuel_type", "quantity", "source_depot_id", "route_id", "status", "created_tick", "expected_arrival_tick")
    return [{k: a.get(k) for k in keys} for a in ctx.world.allocations
            if a.get("destination_station_id") == ctx.subject.station_id and a.get("status") in ACTIVE_ALLOCATION
            and (not ctx.subject.fuel_type or a.get("fuel_type") == ctx.subject.fuel_type)]


@metric("recent_allocations", description="The latest allocations to the station, including delivered and failed ones")
def recent_allocations(ctx: MetricContext) -> Any:
    if not ctx.subject.station_id:
        return None
    keys = ("id", "fuel_type", "quantity", "source_depot_id", "status", "created_tick",
            "actual_arrival_tick", "failure_reason")
    rows = [a for a in ctx.world.allocations if a.get("destination_station_id") == ctx.subject.station_id]
    rows.sort(key=lambda a: a.get("created_tick") or 0, reverse=True)
    return [{k: a.get(k) for k in keys} for a in rows[: int(ctx.params.get("recent_allocations", 5))]]


@metric("routes", description="Routes into the station: status, transit time, max shipment, which one was chosen")
def routes(ctx: MetricContext) -> Any:
    if not ctx.subject.station_id:
        return None
    keys = ("id", "source_depot_id", "status", "transit_ticks", "max_shipment")
    rows = sorted(ctx.world.routes_to(ctx.subject.station_id), key=lambda r: r.get("transit_ticks") or 0)
    return [{**{k: r.get(k) for k in keys}, "chosen": r.get("id") == ctx.subject.route_id} for r in rows]


# ---------- depot ----------

def _open_for_depot(ctx: MetricContext) -> list[dict[str, Any]]:
    return [r for r in ctx.open_recommendations if r.get("depot_id") == ctx.subject.depot_id]


@metric("depot", description="Source depot status, stock, dispatch capacity left this tick")
def depot(ctx: MetricContext) -> Any:
    d = ctx.world.depots.get(ctx.subject.depot_id or "")
    if d is None:
        return None
    capacity, inventory = d.get("capacity") or {}, d.get("inventory") or {}
    return {
        **{k: d.get(k) for k in ("id", "name", "region_id", "status")},
        "dispatch_capacity_per_tick_l": d.get("dispatch_capacity_per_tick"),
        "dispatch_left_this_tick_l": _r(float(d.get("dispatch_capacity_per_tick") or 0) - ctx.world.dispatch_used(d["id"])),
        "reserve_l": ctx.rules.get("DEPOT_RESERVE_LITERS"),
        "fuels": {fuel: {"inventory_l": _r(inventory.get(fuel, 0)), "capacity_l": _r(capacity[fuel])}
                  for fuel in ctx.fuels(capacity)},
    }


@metric("depot_commitments", description="Open (pending / approved) recommendations from the depot and the stock left after them")
def depot_commitments(ctx: MetricContext) -> Any:
    d = ctx.world.depots.get(ctx.subject.depot_id or "")
    if d is None:
        return None
    rows = _open_for_depot(ctx)
    inventory = d.get("inventory") or {}
    return {
        "open": [{k: r.get(k) for k in ("id", "station_id", "fuel_type", "quantity", "status", "risk")} for r in rows],
        "stock_after_open_l": {
            fuel: _r(float(inventory.get(fuel, 0)) - sum(float(r["quantity"]) for r in rows if r.get("fuel_type") == fuel))
            for fuel in ctx.fuels(inventory)
        },
    }


@metric("depot_stations", description="Forecasts of every station the depot can ship to, and their total demand rate")
def depot_stations(ctx: MetricContext) -> Any:
    if not ctx.subject.depot_id:
        return None
    served = sorted({r["destination_station_id"] for r in ctx.world.routes.values()
                     if r.get("source_depot_id") == ctx.subject.depot_id})
    out: dict[str, Any] = {}
    for fuel in ctx.fuels(ctx.world.fuel_types):
        rows = [ctx.snapshot.forecasts[(s, fuel)] for s in served if (s, fuel) in ctx.snapshot.forecasts]
        keys = ("station_id", "risk", "inventory_l", "incoming_l", "rate_l_per_tick", "cover_ticks", "free_space_l")
        out[fuel] = {
            "total_rate_l_per_tick": _r(sum(f.rate_per_tick or 0 for f in rows)),
            "stations": [{**{k: _forecast(f)[k] for k in keys}, "is_subject": f.station_id == ctx.subject.station_id}
                         for f in rows],
        }
    return out


@metric("supply", description="Ship arrivals not yet unloaded at the depot (or everywhere)")
def supply(ctx: MetricContext) -> Any:
    keys = ("id", "depot_id", "fuel_type", "quantity", "planned_tick", "status")
    return [{k: s.get(k) for k in keys} for s in ctx.world.supply
            if s.get("status") != "ARRIVED"
            and (not ctx.subject.depot_id or s.get("depot_id") == ctx.subject.depot_id)
            and (not ctx.subject.fuel_type or s.get("fuel_type") == ctx.subject.fuel_type)]


# ---------- crises and the network ----------

@metric("events", description="ACTIVE and SCHEDULED crises that touch the subject (station, region, depot, route)")
def events(ctx: MetricContext) -> Any:
    st = _subject_station(ctx) or {}
    targets = {"station_ids": ctx.subject.station_id, "region_ids": st.get("region_id"),
               "depot_ids": ctx.subject.depot_id, "route_ids": ctx.subject.route_id}

    def touches(event: dict[str, Any]) -> bool:
        params = event.get("parameters") or {}
        # only filters we can check against the subject; none -> keep it (no filter, or a general question)
        present = [k for k in targets if k in params and targets[k]]
        return not present or any(not params[k] or targets[k] in params[k] for k in present)

    keys = ("id", "type", "status", "start_tick", "end_tick", "parameters")
    return [{k: e.get(k) for k in keys} for e in ctx.world.events
            if e.get("status") in ("ACTIVE", "SCHEDULED") and touches(e)]


@metric("open_recommendations", description="Open recommendations for the subject station (or depot, or all), "
                                            "other than the action itself")
def open_recommendations(ctx: MetricContext) -> Any:
    own = (ctx.subject.action or {}).get("id") if (ctx.subject.action or {}).get("kind") == "recommendation" else None
    rows = [r for r in ctx.open_recommendations if r.get("id") != own]
    if ctx.subject.station_id:
        rows = [r for r in rows if r.get("station_id") == ctx.subject.station_id]
    elif ctx.subject.depot_id:
        rows = [r for r in rows if r.get("depot_id") == ctx.subject.depot_id]
    keys = ("id", "tick", "station_id", "fuel_type", "depot_id", "route_id", "quantity", "risk", "status", "reasons")
    return [{k: r.get(k) for k in keys} for r in rows]


@metric("network", description="Network-wide score: service level, served / unmet demand, failures")
def network(ctx: MetricContext) -> Any:
    return ctx.world.metrics


@metric("network_overview", description="Stations/depots/routes that are not in their normal state")
def network_overview(ctx: MetricContext) -> Any:
    def not_normal(rows: dict[str, dict[str, Any]], normal: str) -> list[dict[str, Any]]:
        return [{"id": i, "status": row.get("status")} for i, row in rows.items() if row.get("status") != normal]
    w = ctx.world
    return {
        "stations": len(w.stations), "depots": len(w.depots), "routes": len(w.routes),
        "stations_not_open": not_normal(w.stations, "OPEN"), "depots_not_open": not_normal(w.depots, "OPEN"),
        "routes_not_available": not_normal(w.routes, "AVAILABLE"),
    }


@metric("outlook", description="Predictor outlook: network fuel left, rationing, depot overflow, cost of doing nothing")
def outlook(ctx: MetricContext) -> Any:
    return ctx.snapshot.outlook or None


@metric("planner", description="The last planner run: which planner, status, budgets")
def planner(ctx: MetricContext) -> Any:
    return ctx.snapshot.planner_info or None


@metric("incidents", description="Detector incidents: related alerts grouped into one story")
def incidents(ctx: MetricContext) -> Any:
    return ctx.snapshot.incidents or None
