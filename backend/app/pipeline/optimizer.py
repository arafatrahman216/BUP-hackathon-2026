"""Decide stage, optimizer version (intelligence-plan X1-X5, X8). Fallback: RulePlanner.

Two levels, both solved with PuLP (HiGHS, CBC as a backup solver):

1. Strategic LP (only for fuels in rationing mode): one window over the remaining days of fuel.
   Maximize the fair coverage phi (every station gets at least phi x its demand), then total served,
   under depot stock + remaining ships, dispatch limits and road capacity. Output: a fuel budget per
   station for the next H ticks (soft cap in the tactical MIP).

2. Tactical MIP-MPC over H ticks (only t = 0 is sent; replanned every tick):
   x[r,f,t] liters on road r departing at t; binary truck n[r,f] at t = 0 with a minimum size.
   Station:  I[t+1] = I[t] + landed[t] - served[t] - tank_overflow[t],  I[t] + landed[t] - overflow <= cap
   Creation: I[t] + sum_r x[r,f,t] <= cap   (the simulator's DESTINATION_CAPACITY rule)
   Depot:    J[t+1] = J[t] + ships[t] - sum_r x[r,f,t] - depot_overflow[t],  J[t] + ships[t] - overflow <= cap
   Dispatch: sum over roads and fuels from a depot <= dispatch limit (minus what's already used now)
   Roads/stations closed now or by known crises -> x = 0.
   Objective (weighted lexicographic): unserved >> waste >> over-budget >> road length >> trucks.
"""

import math
import time
from typing import Any

import pulp

from app.pipeline.twin import Shipment, fixed_arrivals, network_outlook, project, route_open, station_open, supply_arrivals
from app.pipeline.types import Blocked, Forecast, Plan, World

W_UNMET, W_WASTE, W_BUFFER, W_BUDGET, W_ROAD, W_TRUCK, W_KEEP = 1000.0, 100.0, 20.0, 10.0, 0.01, 1.0, 0.05
BUFFER_TICKS = 4  # keep this many ticks of demand in the tank when possible (soft)


class PlannerFailed(RuntimeError):
    pass


def _solve(problem: pulp.LpProblem, time_limit: float) -> str:
    for solver in (pulp.HiGHS(msg=False, timeLimit=time_limit), pulp.PULP_CBC_CMD(msg=False, timeLimit=time_limit)):
        try:
            problem.solve(solver)
        except Exception:  # solver missing or crashed -> try the next one
            continue
        status = pulp.LpStatus[problem.status]
        if status in ("Optimal", "Not Solved") and problem.objective.value() is not None:
            return status
    raise PlannerFailed("no solver found a solution")


def strategic_budgets(world: World, forecasts: dict[tuple[str, str], Forecast], horizon: int,
                      outlook: dict[str, Any], time_limit: float) -> dict[tuple[str, str], float]:
    """Fair-share fuel budget per (station, fuel) for the next `horizon` ticks, for rationing fuels."""
    fuels = [f for f, o in outlook.get("fuels", {}).items() if o.get("rationing") and o.get("days_left")]
    if not fuels:
        return {}
    tpd = max(1, 1440 // world.tick_minutes)
    window = {f: max(horizon, min(7 * tpd, int(outlook["fuels"][f]["days_left"] * tpd) or horizon)) for f in fuels}
    prob = pulp.LpProblem("strategic", pulp.LpMaximize)
    ship, served, phi = {}, {}, {}
    for f in fuels:
        phi[f] = pulp.LpVariable(f"phi_{f}", 0, 1)
        for rid, r in world.routes.items():
            if f in world.stations[r["destination_station_id"]].get("capacity", {}):
                cap = float(r["max_shipment"]) * window[f]
                ship[(rid, f)] = pulp.LpVariable(f"ship_{rid}_{f}", 0, cap)
        for s, st in world.stations.items():
            fc = forecasts.get((s, f))
            if fc is None:
                continue
            demand = (fc.daily_rate_per_tick or fc.rate_per_tick or 0.0) * window[f]
            served[(s, f)] = pulp.LpVariable(f"served_{s}_{f}", 0, demand)
            into = [ship[(rid, f)] for rid, r in world.routes.items() if r["destination_station_id"] == s and (rid, f) in ship]
            prob += served[(s, f)] <= fc.inventory + fc.incoming + pulp.lpSum(into)
            prob += served[(s, f)] >= phi[f] * demand
        for d, dep in world.depots.items():
            out = [ship[(rid, f)] for rid, r in world.routes.items() if r["source_depot_id"] == d and (rid, f) in ship]
            more = sum(float(x.get("quantity") or 0) for x in world.supply if x.get("depot_id") == d
                       and x.get("fuel_type") == f and x.get("status") != "ARRIVED")
            prob += pulp.lpSum(out) <= float(dep["inventory"].get(f, 0)) + more
    for d, dep in world.depots.items():
        out = [v for (rid, f), v in ship.items() if world.routes[rid]["source_depot_id"] == d]
        prob += pulp.lpSum(out) <= float(dep.get("dispatch_capacity_per_tick") or 0) * max(window.values())
    prob += 1e6 * pulp.lpSum(phi.values()) + pulp.lpSum(served.values()) \
        - pulp.lpSum(W_ROAD * int(world.routes[rid]["transit_ticks"]) * v for (rid, f), v in ship.items())
    _solve(prob, time_limit)
    budgets: dict[tuple[str, str], float] = {}
    for (rid, f), v in ship.items():
        s = world.routes[rid]["destination_station_id"]
        budgets[(s, f)] = budgets.get((s, f), 0.0) + (v.value() or 0.0) * horizon / window[f]
    return budgets


class OptimizerPlanner:
    name = "optimizer"

    def __init__(self, horizon: int, min_shipment: float, time_limit: float, trigger_days: float) -> None:
        self.horizon, self.min_shipment, self.time_limit, self.trigger_days = horizon, min_shipment, time_limit, trigger_days
        self.last: dict[str, Any] = {}

    def plan(self, world: World, forecasts: dict[tuple[str, str], Forecast],
             skip: set[tuple[str, str]]) -> tuple[list[Plan], list[Blocked]]:
        started = time.perf_counter()
        H = min((len(f.demand_path) for f in forecasts.values() if f.demand_path), default=0) or self.horizon
        demand = {k: (f.demand_path or [f.rate_per_tick or 0.0] * H)[:H] for k, f in forecasts.items()}
        daily = {k: f.daily_rate_per_tick or f.rate_per_tick for k, f in forecasts.items()}
        outlook = network_outlook(world, daily, self.trigger_days)
        budgets = strategic_budgets(world, forecasts, H, outlook, self.time_limit) if outlook["rationing"] else {}

        now, T = world.tick, range(H)
        landed_fixed = fixed_arrivals(world)
        ships = supply_arrivals(world)
        prob = pulp.LpProblem("tactical", pulp.LpMinimize)
        x, n = {}, {}
        for rid, r in world.routes.items():
            s, d, L = r["destination_station_id"], r["source_depot_id"], int(r["transit_ticks"])
            for f in world.fuel_types:
                if f not in world.stations[s].get("capacity", {}) or f not in world.depots[d].get("capacity", {}):
                    continue
                for t in T:
                    if t + L >= H + 1 or not route_open(world, rid, now + t) or not station_open(world, s, now + t):
                        continue
                    if t == 0 and (s, f) in skip:
                        continue
                    x[(rid, f, t)] = pulp.LpVariable(f"x_{rid}_{f}_{t}", 0, float(r["max_shipment"]))
                for t in T:  # whole trucks with a minimum size on every tick (no just-in-time trickle)
                    if (rid, f, t) in x:
                        n[(rid, f, t)] = pulp.LpVariable(f"n_{rid}_{f}_{t}", cat="Binary")
                        prob += x[(rid, f, t)] <= float(r["max_shipment"]) * n[(rid, f, t)]
                        prob += x[(rid, f, t)] >= self.min_shipment * n[(rid, f, t)]

        unmet_terms, waste_terms, keep_terms, buffer_terms = [], [], [], []
        for (s, f), path in demand.items():
            st = world.stations[s]
            cap = float(st["capacity"].get(f, 0))
            level = float(st["inventory"].get(f, 0))
            I_prev = level
            into = [(rid, int(r["transit_ticks"])) for rid, r in world.routes.items() if r["destination_station_id"] == s]
            for t in T:
                served = pulp.LpVariable(f"sv_{s}_{f}_{t}", 0, path[t] if station_open(world, s, now + t) else 0.0)
                over = pulp.LpVariable(f"ov_{s}_{f}_{t}", 0)
                landed = landed_fixed.get((s, f, t), 0.0) + pulp.lpSum(
                    x[(rid, f, t - L)] for rid, L in into if (rid, f, t - L) in x)
                prob += I_prev + pulp.lpSum(x[(rid, f, t)] for rid, _ in into if (rid, f, t) in x) <= cap  # creation rule
                prob += I_prev + landed - over <= cap
                I_next = pulp.LpVariable(f"I_{s}_{f}_{t + 1}", 0, cap)
                prob += I_next == I_prev + landed - served - over
                unmet_terms.append(path[t] - served)
                waste_terms.append(over)
                want = min(cap, sum(path[t + 1:t + 1 + BUFFER_TICKS]))
                if want > 0:
                    short = pulp.LpVariable(f"sh_{s}_{f}_{t}", 0, want)
                    prob += short >= want - I_next
                    buffer_terms.append(short)
                I_prev = I_next
            keep_terms.append(I_prev)

        for d, dep in world.depots.items():
            used_now = world.dispatch_used(d)
            limit = float(dep.get("dispatch_capacity_per_tick") or 0)
            for t in T:
                out_t = [v for (rid, f, tt), v in x.items() if tt == t and world.routes[rid]["source_depot_id"] == d]
                if out_t:
                    prob += pulp.lpSum(out_t) <= limit - (used_now if t == 0 else 0.0)
            for f, level in dep.get("inventory", {}).items():
                cap = float(dep["capacity"].get(f, 0))
                J_prev = float(level)
                for t in T:
                    over = pulp.LpVariable(f"dov_{d}_{f}_{t}", 0)
                    out = pulp.lpSum(v for (rid, ff, tt), v in x.items()
                                     if ff == f and tt == t and world.routes[rid]["source_depot_id"] == d)
                    arrive = ships.get((d, f, t), 0.0)
                    prob += J_prev + arrive - over <= cap
                    J_next = pulp.LpVariable(f"J_{d}_{f}_{t + 1}", 0, cap)
                    prob += J_next == J_prev + arrive - out - over
                    waste_terms.append(over)
                    J_prev = J_next

        budget_terms = []
        for (s, f), b in budgets.items():
            into = [v for (rid, ff, t), v in x.items() if ff == f and world.routes[rid]["destination_station_id"] == s]
            if into:
                extra = pulp.LpVariable(f"bo_{s}_{f}", 0)
                prob += pulp.lpSum(into) <= b + extra
                budget_terms.append(extra)

        road = pulp.lpSum(int(world.routes[rid]["transit_ticks"]) * v for (rid, f, t), v in x.items())
        prob += (W_UNMET * pulp.lpSum(unmet_terms) + W_WASTE * pulp.lpSum(waste_terms)
                 + W_BUFFER * pulp.lpSum(buffer_terms) + W_BUDGET * pulp.lpSum(budget_terms) + W_ROAD * road + W_TRUCK * pulp.lpSum(n.values())
                 - W_KEEP * pulp.lpSum(keep_terms))
        status = _solve(prob, self.time_limit)

        plans, planned_later = [], {}
        for (rid, f, t), v in x.items():
            qty = math.floor((v.value() or 0.0) / 100) * 100
            if qty < self.min_shipment:
                continue
            r = world.routes[rid]
            s = r["destination_station_id"]
            if t > 0:
                planned_later.setdefault((s, f), now + t)
                continue
            fc = forecasts[(s, f)]
            over_budget = (s, f) in budgets and qty > budgets[(s, f)] + self.min_shipment
            plans.append(Plan(station_id=s, fuel_type=f, depot_id=r["source_depot_id"], route_id=rid,
                              quantity=float(qty), risk=fc.risk, ticks_until_empty=fc.ticks_until_empty,
                              planner=self.name, confidence=fc.confidence, over_budget=over_budget))
        self._impact(world, demand, H, plans)

        blocked = []
        planned_now = {(p.station_id, p.fuel_type) for p in plans}
        for key, fc in forecasts.items():
            if fc.risk in ("watch", "urgent") and key not in planned_now and key not in skip:
                when = planned_later.get(key)
                reason = (f"wait: planned for tick {when}" if when else
                          "wait: no room, stock or dispatch capacity helps within the horizon")
                blocked.append(Blocked(key[0], key[1], reason))
        self.last = {"status": status, "ms": round((time.perf_counter() - started) * 1000, 1), "variables": len(x),
                     "rationing": outlook["rationing"], "budgets": {f"{s}:{f}": round(b) for (s, f), b in budgets.items()},
                     "planned_later": {f"{s}:{f}": t for (s, f), t in planned_later.items()}}
        return plans, blocked

    def _impact(self, world: World, demand: dict[tuple[str, str], list[float]], H: int, plans: list[Plan]) -> None:
        """P6: run the simulator copy with and without each plan."""
        fn = lambda s, f, k: demand[(s, f)][k] if k < len(demand[(s, f)]) else 0.0  # noqa: E731
        base = project(world, fn, H)
        for p in plans:
            with_plan = project(world, fn, H, [Shipment(0, p.route_id, p.fuel_type, p.quantity)])
            b, w = base.stations[(p.station_id, p.fuel_type)], with_plan.stations[(p.station_id, p.fuel_type)]
            p.impact = {"unmet_before": round(b.unmet), "unmet_after": round(w.unmet),
                        "stockout_tick_before": world.tick + b.stockout_k if b.stockout_k is not None else None,
                        "stockout_tick_after": world.tick + w.stockout_k if w.stockout_k is not None else None,
                        "tank_overflow_after": round(w.tank_overflow)}
