"""Detect stage (intelligence-plan D1-D7). Stateful: one Detector lives in the pipeline state.

- D1 changes: station/road/depot status, multipliers, active and scheduled crises (with countdown),
     silent supply changes (a ship's tick moved or its amount shrank vs first seen), failed trucks
- D2 unusual demand: single-tick z-score (2+ ticks in a row) and CUSUM (running total) on
     log(actual / forecast); the forecast already includes the multiplier, so announced spikes don't fire
- D3 clock: skipped ticks (stale/invalid data and resets are added by the pipeline service)
- D4 reconciliation: depot fuel change vs supply in - trucks out; the gap is wasted (overflow) fuel
- D5 single-route stations: a cut road means no way to refill
- D6 bottlenecks: a depot's dispatch limit full several ticks in a row, trucks past their arrival time
- D7 incidents: active alerts grouped by region into one story that closes itself on recovery

Every alert carries `explained_by` (the crisis behind it, if any) and `since_tick`.
"""

import math
from typing import Any

from app.pipeline.demand_model import Residual, active_at, event_touches
from app.pipeline.types import Alert, World

SEVERITY = {"info": 0, "warning": 1, "critical": 2}


class Detector:
    def __init__(self, z: float = 3.0, cusum_k: float = 0.05, cusum_h: float = 0.5, min_liters: float = 20.0) -> None:
        self.z, self.k, self.h, self.min_liters = z, cusum_k, cusum_h, min_liters
        self.prev: World | None = None
        self.first_supply: dict[str, tuple[int, float]] = {}
        self.cusum: dict[tuple[str, str], list[float]] = {}  # [pos, neg, run_of_big_z]
        self.recent_x: dict[tuple[str, str], list[float]] = {}
        self.since: dict[tuple[str, str | None], int] = {}
        self.bottleneck_run: dict[str, int] = {}
        self.demand_flags: dict[tuple[str, str], Alert] = {}
        self.wasted: dict[str, float] = {}  # depot_id -> liters lost to overflow (our observation)
        self.incidents: list[dict[str, Any]] = []
        self._open_incidents: dict[str, dict[str, Any]] = {}

    # ---------- public ----------
    def detect(self, world: World, residuals: list[Residual] | None = None) -> list[Alert]:
        alerts: list[Alert] = []
        self._changes(world, alerts)
        self._demand(world, residuals or [], alerts)
        self._clock(world, alerts)
        self._reconcile(world, alerts)
        self._single_route(world, alerts)
        self._bottlenecks(world, alerts)
        self._finish(world, alerts)
        self.prev = world
        return alerts

    # ---------- helpers ----------
    def _region(self, world: World, entity_id: str | None) -> str | None:
        if entity_id in world.stations:
            return world.stations[entity_id].get("region_id")
        if entity_id in world.depots:
            return world.depots[entity_id].get("region_id")
        if entity_id in world.routes:
            return world.stations.get(world.routes[entity_id].get("destination_station_id"), {}).get("region_id")
        return None

    @staticmethod
    def _event_label(e: dict[str, Any]) -> str:
        return f"event {e.get('id')} ({e.get('type')})"

    def _explains(self, world: World, types: tuple[str, ...], **touch: Any) -> str | None:
        for e in world.events:
            if e.get("type") in types and e.get("status") == "ACTIVE" and event_touches(e, **touch):
                return self._event_label(e)
        return None

    def _hours(self, world: World, ticks: float) -> str:
        return f"~{ticks * world.tick_minutes / 60:.1f} h"

    # ---------- D1 ----------
    def _changes(self, world: World, alerts: list[Alert]) -> None:
        for sid, st in world.stations.items():
            name = st.get("name", sid)
            if st.get("status") != "OPEN":
                alerts.append(Alert("critical", "STATION_OUTAGE", f"{name} is in {st.get('status')}", sid,
                                    self._explains(world, ("station_outage",), station=st)))
            mult = float(st.get("demand_multiplier") or 1.0)
            if mult != 1.0:
                alerts.append(Alert("warning", "DEMAND_SPIKE", f"{name} demand x{mult:g}", sid,
                                    self._explains(world, ("demand_spike",), station=st)))
        for rid, r in world.routes.items():
            if r.get("status") != "AVAILABLE":
                alerts.append(Alert("critical", "ROUTE_DISRUPTED", f"Route {rid} is {r.get('status')}", rid,
                                    self._explains(world, ("route_disruption",), route_id=rid)))
        for did, d in world.depots.items():
            if d.get("status") != "OPEN":
                alerts.append(Alert("warning", "DEPOT_CONSTRAINED", f"{d.get('name', did)} is {d.get('status')} "
                                    "(label only: shipments still work)", did,
                                    self._explains(world, ("depot_constraint",), depot_id=did)))
        for e in world.events:
            label = self._event_label(e)
            if e.get("status") == "ACTIVE":
                left = int(e.get("end_tick") or world.tick) - world.tick
                alerts.append(Alert("critical", "CRISIS_ACTIVE", f"{e.get('type')} active, ends in {left} ticks "
                                    f"({self._hours(world, left)})", str(e.get("id")), label))
            elif e.get("status") == "SCHEDULED":
                wait = int(e.get("start_tick") or world.tick) - world.tick
                alerts.append(Alert("warning" if wait <= 8 else "info", "CRISIS_SCHEDULED",
                                    f"{e.get('type')} starts in {wait} ticks ({self._hours(world, wait)}) at tick "
                                    f"{e.get('start_tick')}", str(e.get("id")), label))
        for s in world.supply:
            sid, planned, qty = s.get("id"), int(s.get("planned_tick") or 0), float(s.get("quantity") or 0)
            first = self.first_supply.setdefault(sid, (planned, qty))
            if s.get("status") == "ARRIVED":
                continue
            why = self._explains(world, ("shipment_delay", "supply_shortfall"), depot_id=s.get("depot_id")) or \
                next((self._event_label(e) for e in world.events if e.get("type") in ("shipment_delay", "supply_shortfall")
                      and event_touches(e, depot_id=s.get("depot_id"))), None)
            if s.get("status") == "DELAYED" or planned > first[0]:
                alerts.append(Alert("warning", "SUPPLY_DELAYED", f"{s.get('depot_id')} {s.get('fuel_type')} ship moved "
                                    f"from tick {first[0]} to {planned}", sid, why))
            if qty < first[1] - 1:
                alerts.append(Alert("warning", "SUPPLY_SHORTFALL", f"{s.get('depot_id')} {s.get('fuel_type')} ship cut "
                                    f"from {first[1]:,.0f} to {qty:,.0f} L", sid, why))
        for a in world.allocations[:50]:
            if a.get("status") == "FAILED" and int(a.get("created_tick") or 0) >= world.tick - 8:
                alerts.append(Alert("critical", "SHIPMENT_FAILED", f"Allocation {a.get('id')} failed: "
                                    f"{a.get('failure_reason')}", str(a.get("id")),
                                    self._explains(world, ("route_disruption",), route_id=a.get("route_id"))))
        last_tick = max((row.get("tick", 0) for row in world.history), default=None)
        unmet = sum(float(r.get("unmet_liters") or 0) for r in world.history if r.get("tick") == last_tick)
        if unmet > 0:
            alerts.append(Alert("warning", "UNMET_DEMAND", f"{unmet:,.0f} L of demand went unserved at tick {last_tick}"))

    # ---------- D2 ----------
    def _demand(self, world: World, residuals: list[Residual], alerts: list[Alert]) -> None:
        for r in residuals:
            key = (r.station_id, r.fuel_type)
            if r.predicted < self.min_liters and r.actual < self.min_liters:
                continue  # night-time noise
            x = math.log((r.actual + 1) / (r.predicted + 1))
            pos, neg, run = self.cusum.get(key, [0.0, 0.0, 0.0])
            pos, neg = max(0.0, pos + x - self.k), max(0.0, neg - x - self.k)
            run = run + 1 if abs(x) / max(r.cv, 1e-6) > self.z else 0
            window = (self.recent_x.get(key, []) + [x])[-8:]
            self.recent_x[key] = window
            if pos > self.h or neg > self.h or run >= 2:
                size = math.exp(sum(window[-4:]) / len(window[-4:])) - 1
                st = world.stations.get(r.station_id, {})
                how = "running total (CUSUM)" if (pos > self.h or neg > self.h) else "2+ ticks beyond the normal range"
                self.demand_flags[key] = Alert(
                    "warning", "DEMAND_ANOMALY",
                    f"{st.get('name', r.station_id)} {r.fuel_type} demand {size:+.0%} vs forecast ({how})",
                    r.station_id, self._explains(world, ("demand_spike",), station=st) or "unexplained")
                pos = neg = run = 0.0
            elif key in self.demand_flags and abs(sum(window[-4:]) / len(window[-4:])) < self.k:
                del self.demand_flags[key]  # back to normal
            self.cusum[key] = [pos, neg, run]
        alerts.extend(self.demand_flags.values())

    # ---------- D3 ----------
    def _clock(self, world: World, alerts: list[Alert]) -> None:
        if self.prev and world.tick > self.prev.tick + 1:
            alerts.append(Alert("info", "TICKS_SKIPPED", f"Ticks {self.prev.tick + 1}-{world.tick - 1} were not seen "
                                "(simulator faster than the pipeline)"))

    # ---------- D4 ----------
    def _reconcile(self, world: World, alerts: list[Alert]) -> None:
        prev = self.prev
        if not prev or world.tick <= prev.tick:
            return
        arrived = {}
        for s in world.supply:
            at = s.get("actual_tick")
            if s.get("status") == "ARRIVED" and at is not None and prev.tick < int(at) <= world.tick:
                key = (s["depot_id"], s["fuel_type"])
                arrived[key] = arrived.get(key, 0.0) + float(s.get("quantity") or 0)
        sent = {}
        for a in world.allocations:
            if prev.tick < int(a.get("created_tick") or -1) <= world.tick and a.get("status") != "CANCELLED":
                key = (a["source_depot_id"], a["fuel_type"])
                sent[key] = sent.get(key, 0.0) + float(a.get("quantity") or 0)
        for did, d in world.depots.items():
            for f, level in d.get("inventory", {}).items():
                before = float(prev.depots.get(did, {}).get("inventory", {}).get(f, level))
                expected = before + arrived.get((did, f), 0.0) - sent.get((did, f), 0.0)
                gap = expected - float(level)
                if arrived.get((did, f)) and gap > 1:
                    self.wasted[did] = self.wasted.get(did, 0.0) + gap
                    alerts.append(Alert("warning", "FUEL_WASTED", f"{d.get('name', did)} {f}: {gap:,.0f} L of an arriving "
                                        "ship did not fit (depot full)", did))
                elif abs(gap) > max(100.0, 0.02 * float(d["capacity"].get(f, 0))):
                    alerts.append(Alert("warning", "INVENTORY_MISMATCH", f"{d.get('name', did)} {f} changed by "
                                        f"{float(level) - before:+,.0f} L, expected {expected - before:+,.0f} L", did,
                                        "unexplained"))

    # ---------- D5 ----------
    def _single_route(self, world: World, alerts: list[Alert]) -> None:
        for sid, st in world.stations.items():
            routes = world.routes_to(sid)
            if len(routes) != 1:
                continue
            rid = routes[0]["id"]
            if routes[0].get("status") != "AVAILABLE":
                alerts.append(Alert("critical", "SINGLE_ROUTE_CUT", f"{st.get('name', sid)} has only one road ({rid}) "
                                    "and it is cut: no way to refill", sid,
                                    self._explains(world, ("route_disruption",), route_id=rid)))
            for e in world.events:
                if e.get("type") == "route_disruption" and e.get("status") == "SCHEDULED" and event_touches(e, route_id=rid):
                    wait = int(e.get("start_tick") or world.tick) - world.tick
                    alerts.append(Alert("warning", "SINGLE_ROUTE_THREAT", f"{st.get('name', sid)}'s only road closes in "
                                        f"{wait} ticks: pre-fill now", sid, self._event_label(e)))

    # ---------- D6 ----------
    def _bottlenecks(self, world: World, alerts: list[Alert]) -> None:
        for did, d in world.depots.items():
            cap = float(d.get("dispatch_capacity_per_tick") or 0)
            full = cap > 0 and world.dispatch_used(did) >= 0.95 * cap
            self.bottleneck_run[did] = self.bottleneck_run.get(did, 0) + 1 if full else 0
            if self.bottleneck_run[did] >= 3:
                alerts.append(Alert("warning", "DISPATCH_BOTTLENECK", f"{d.get('name', did)} dispatch limit full for "
                                    f"{self.bottleneck_run[did]} ticks", did))
        for a in world.allocations[:50]:
            eta = a.get("expected_arrival_tick")
            if a.get("status") == "IN_TRANSIT" and eta is not None and int(eta) < world.tick:
                alerts.append(Alert("warning", "SHIPMENT_OVERDUE", f"Allocation {a.get('id')} was due at tick {eta}",
                                    str(a.get("id"))))

    # ---------- lifecycle + D7 ----------
    def _finish(self, world: World, alerts: list[Alert]) -> None:
        seen = set()
        for a in alerts:
            key = (a.code, a.entity_id)
            seen.add(key)
            a.since_tick = self.since.setdefault(key, world.tick)
            a.region_id = self._region(world, a.entity_id)
        self.since = {k: v for k, v in self.since.items() if k in seen}
        alerts.sort(key=lambda a: -SEVERITY.get(a.level, 0))

        active: dict[str, list[Alert]] = {}
        for a in alerts:
            if a.level != "info":
                active.setdefault(a.region_id or "network", []).append(a)
        for region, items in active.items():
            inc = self._open_incidents.get(region)
            if inc is None:
                inc = {"id": len(self.incidents) + 1, "region_id": region, "opened_tick": world.tick,
                       "resolved_tick": None, "status": "open", "timeline": []}
                self._open_incidents[region] = inc
                self.incidents.append(inc)
            codes = sorted({a.code for a in items})
            if not inc["timeline"] or inc["timeline"][-1]["codes"] != codes:
                inc["timeline"].append({"tick": world.tick, "codes": codes})
            inc["alerts"] = [a.to_dict() for a in items]
            inc["combined"] = len({a.code for a in items if a.code not in ("UNMET_DEMAND",)}) >= 2
            inc["explained_by"] = sorted({a.explained_by for a in items if a.explained_by and a.explained_by != "unexplained"})
        for region in list(self._open_incidents):
            if region not in active:
                inc = self._open_incidents.pop(region)
                inc.update(status="resolved", resolved_tick=world.tick)
                inc["timeline"].append({"tick": world.tick, "codes": [], "note": "recovered"})
        self.incidents = self.incidents[-20:]


def detect(world: World) -> list[Alert]:
    """Stateless one-shot detection (no history): kept for callers without a Detector."""
    return Detector().detect(world)


__all__ = ["Detector", "detect", "active_at"]
