#!/usr/bin/env python3
"""Build a dataset from the BUP Fuel Supply Simulator by pulling every kind of data it exposes.

Standard library only; no install needed.

Two modes:

  step  (recommended) Pauses the simulator and advances it one tick at a time with
        POST /admin/step, taking a full snapshot after every tick. You get every tick
        with no gaps, and the run is deterministic (same seed, same data).

            python simulator/collect_dataset.py step --ticks 960 --reset

  live  Leaves the clock alone and polls while the simulator runs. It snapshots whenever
        the tick changes. At SIMULATION_SPEED=8 some ticks can pass between polls; those
        snapshots are missed, but demand history and audit are still captured without
        gaps (they are append-only).

            python simulator/collect_dataset.py live --duration 300

Output (default: simulator/dataset/<timestamp>/):

  regions.csv            static: regions and their demand_factor
  instance.csv           per tick: tick, sim_time, status, wall_time, stale flag
  depot_inventory.csv    per tick x depot x fuel: status, inventory, capacity, dispatch cap
  station_inventory.csv  per tick x station x fuel: status, multiplier, inventory, capacity
  route_status.csv       per tick x route: status, transit_ticks, max_shipment
  metrics.csv            per tick: served/unmet liters, service_level, allocation stats
  demand_history.csv     one row per station x fuel x tick (deduplicated by id)
  audit.csv              simulator audit log (deduplicated by id)
  supply_arrivals.csv    final state of every scheduled supply ship
  events.csv             final state of every crisis event
  allocations.csv        final state of every shipment
  faults.csv             final state of every injected fault
  entity_changes.csv     every status change of a ship / event / allocation / fault, with tick
  snapshots.jsonl        raw JSON of every snapshot (full fidelity)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FUELS = ("DIESEL", "PETROL", "OCTANE")
ROWS_PER_TICK = 12  # 4 stations x 3 fuels in demand history
HISTORY_LIMIT = 2000  # server-side max for /v1/demand-history
AUDIT_LIMIT = 1000  # server-side max for /admin/audit


class SimClient:
    def __init__(self, base_url: str, retries: int = 5, timeout: float = 10.0) -> None:
        self.base = base_url.rstrip("/")
        self.retries = retries
        self.timeout = timeout
        self.last_stale = False

    def _request(self, method: str, path: str):
        delay = 0.25
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(self.base + path, method=method,
                                         headers={"Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    self.last_stale = resp.headers.get("X-Simulator-Stale", "").lower() == "true"
                    body = resp.read()
                    return json.loads(body) if body else None
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                # 4xx other than 429 won't get better with retries
                if isinstance(exc, urllib.error.HTTPError) and 400 <= exc.code < 500 and exc.code != 429:
                    raise
                if attempt == self.retries:
                    raise
                print(f"  ! {method} {path} failed ({exc}); retry in {delay:.2f}s", file=sys.stderr)
                time.sleep(delay)
                delay = min(delay * 2, 5.0)

    def get(self, path: str):
        return self._request("GET", path)

    def post(self, path: str):
        return self._request("POST", path)


class CsvSink:
    """Append-only CSV writer. The header is fixed by the first row it gets."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None
        self._writer = None

    def write(self, rows: list[dict]) -> None:
        if not rows:
            return
        if self._writer is None:
            self._fh = self.path.open("w", newline="")
            self._writer = csv.DictWriter(self._fh, fieldnames=list(rows[0].keys()), extrasaction="ignore")
            self._writer.writeheader()
        self._writer.writerows(rows)
        self._fh.flush()

    def close(self) -> None:
        if self._fh:
            self._fh.close()


def flat(obj: dict) -> dict:
    """Flatten one level of nested dicts ({"parameters": {"x": 1}} -> parameters_x) and JSON-encode lists."""
    out = {}
    for k, v in obj.items():
        if isinstance(v, dict):
            for k2, v2 in v.items():
                out[f"{k}_{k2}"] = json.dumps(v2) if isinstance(v2, (list, dict)) else v2
        elif isinstance(v, list):
            out[k] = json.dumps(v)
        else:
            out[k] = v
    return out


def write_table(path: Path, rows: list[dict]) -> None:
    rows = [flat(r) for r in rows]
    fields: list[str] = []
    for r in rows:
        fields += [k for k in r if k not in fields]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields or ["empty"])
        w.writeheader()
        w.writerows(rows)


class Collector:
    def __init__(self, client: SimClient, out_dir: Path, with_admin: bool) -> None:
        self.c = client
        self.out = out_dir
        self.with_admin = with_admin
        out_dir.mkdir(parents=True, exist_ok=True)
        names = ["instance", "depot_inventory", "station_inventory", "route_status", "metrics",
                 "demand_history", "audit", "entity_changes"]
        self.sinks = {n: CsvSink(out_dir / f"{n}.csv") for n in names}
        self.raw = (out_dir / "snapshots.jsonl").open("w")
        self.seen_history: set[int] = set()
        self.seen_audit: set[int] = set()
        # keyed entities: kind -> id -> latest row
        self.entities: dict[str, dict] = {"supply_arrivals": {}, "events": {}, "allocations": {}, "faults": {}}
        self.snapshots = 0
        self.last_tick: int | None = None
        self.missed_ticks = 0

    # ---- one-off data ----
    def collect_static(self) -> None:
        write_table(self.out / "regions.csv", self.c.get("/v1/regions"))

    def backfill_history(self) -> None:
        """Pull as much past demand history as the API allows (2000 rows per station -> ~666 ticks)."""
        rows = []
        for st in self.c.get("/v1/stations"):
            rows += self.c.get(f"/v1/demand-history?station_id={st['id']}&limit={HISTORY_LIMIT}")
        self._add_history(rows)
        print(f"backfilled {len(rows)} demand-history rows")

    # ---- per-tick snapshot ----
    def snapshot(self) -> int:
        c = self.c
        wall = datetime.now(timezone.utc).isoformat()
        inst = c.get("/v1/instance")
        stale = c.last_stale
        tick, sim_time = inst["tick"], inst["sim_time"]

        depots = c.get("/v1/depots")
        stations = c.get("/v1/stations")
        routes = c.get("/v1/routes")
        metrics = c.get("/v1/metrics")
        arrivals = c.get("/v1/supply-arrivals")
        events = c.get("/v1/events")
        allocations = c.get("/v1/allocations")

        gap = 1 if self.last_tick is None else max(tick - self.last_tick, 1)
        if self.last_tick is not None and gap > 1:
            self.missed_ticks += gap - 1
        limit = min(HISTORY_LIMIT, ROWS_PER_TICK * (gap + 2))
        history = c.get(f"/v1/demand-history?limit={limit}")
        if self.last_tick is not None and gap * ROWS_PER_TICK > HISTORY_LIMIT:
            print(f"  ! gap of {gap} ticks is larger than demand-history can return; some rows lost",
                  file=sys.stderr)

        audit, faults = [], []
        if self.with_admin:
            audit = c.get(f"/admin/audit?limit={min(AUDIT_LIMIT, 50 + 20 * gap)}")
            faults = c.get("/admin/faults")

        base = {"tick": tick, "sim_time": sim_time}
        self.sinks["instance"].write([{**base, "status": inst["status"], "tick_minutes": inst["tick_minutes"],
                                       "scenario_id": inst["scenario_id"], "seed": inst["seed"],
                                       "wall_time": wall, "stale": stale}])
        self.sinks["depot_inventory"].write([
            {**base, "depot_id": d["id"], "region_id": d["region_id"], "status": d["status"],
             "dispatch_capacity_per_tick": d["dispatch_capacity_per_tick"], "fuel_type": f,
             "inventory": d["inventory"].get(f), "capacity": d["capacity"].get(f)}
            for d in depots for f in FUELS])
        self.sinks["station_inventory"].write([
            {**base, "station_id": s["id"], "region_id": s["region_id"], "status": s["status"],
             "demand_profile": s["demand_profile"], "demand_multiplier": s["demand_multiplier"],
             "fuel_type": f, "inventory": s["inventory"].get(f), "capacity": s["capacity"].get(f)}
            for s in stations for f in FUELS])
        self.sinks["route_status"].write([{**base, **r} for r in routes])
        self.sinks["metrics"].write([{**base, **metrics}])
        self._add_history(history)
        self._add_audit(audit)
        for kind, rows in (("supply_arrivals", arrivals), ("events", events),
                           ("allocations", allocations), ("faults", faults)):
            self._track(kind, rows, tick)

        self.raw.write(json.dumps({**base, "wall_time": wall, "stale": stale, "instance": inst,
                                   "depots": depots, "stations": stations, "routes": routes,
                                   "metrics": metrics, "supply_arrivals": arrivals, "events": events,
                                   "allocations": allocations, "faults": faults}) + "\n")
        self.snapshots += 1
        self.last_tick = tick
        return tick

    def _add_history(self, rows: list[dict]) -> None:
        new = [r for r in rows if r["id"] not in self.seen_history]
        self.seen_history.update(r["id"] for r in new)
        self.sinks["demand_history"].write(sorted(new, key=lambda r: r["id"]))

    def _add_audit(self, rows: list[dict]) -> None:
        new = [flat(r) for r in rows if r["id"] not in self.seen_audit]
        self.seen_audit.update(r["id"] for r in new)
        # metadata keys vary by action, so keep metadata as one JSON column
        for r in new:
            r.update({"metadata_json": json.dumps({k[len("metadata_json_"):]: r.pop(k)
                                                   for k in list(r) if k.startswith("metadata_json_")})})
        self.sinks["audit"].write(sorted(new, key=lambda r: r["id"]))

    def _track(self, kind: str, rows: list[dict], tick: int) -> None:
        known = self.entities[kind]
        changes = []
        for r in rows:
            old = known.get(r["id"])
            old_status = None if old is None else (old.get("status") if "status" in old else old.get("active"))
            new_status = r.get("status", r.get("active"))
            if old is None or old_status != new_status:
                changes.append({"tick": tick, "kind": kind, "entity_id": r["id"],
                                "old_status": old_status, "new_status": new_status, "row": json.dumps(r)})
            known[r["id"]] = r
        self.sinks["entity_changes"].write(changes)

    def close(self) -> None:
        for kind, rows in self.entities.items():
            if kind == "faults" and not self.with_admin:
                continue
            write_table(self.out / f"{kind}.csv", list(rows.values()))
        for s in self.sinks.values():
            s.close()
        self.raw.close()


def run_step(args, client: SimClient, col: Collector) -> None:
    prev_status = client.get("/v1/instance")["status"]
    client.post("/admin/pause")
    try:
        if args.reset:
            client.post("/admin/reset")
            client.post("/admin/pause")  # reset may restore the start mode
            print("simulator reset to tick 0")
        col.snapshot()
        for i in range(args.ticks):
            client.post("/admin/step")
            tick = col.snapshot()
            if (i + 1) % 96 == 0 or i + 1 == args.ticks:
                print(f"  tick {tick}  ({i + 1}/{args.ticks}, day {(i + 1) / 96:.1f})")
    finally:
        if prev_status == "RUNNING" and not args.leave_paused:
            client.post("/admin/run")


def run_live(args, client: SimClient, col: Collector) -> None:
    deadline = time.monotonic() + args.duration
    col.snapshot()
    while time.monotonic() < deadline:
        try:
            tick = client.get("/v1/instance")["tick"]
        except Exception as exc:  # simulator "unavailable" fault: keep waiting
            print(f"  ! instance unreachable ({exc})", file=sys.stderr)
            time.sleep(1)
            continue
        if tick != col.last_tick:
            try:
                col.snapshot()
            except Exception as exc:
                print(f"  ! snapshot failed at tick {tick} ({exc})", file=sys.stderr)
            if col.snapshots % 100 == 0:
                print(f"  tick {col.last_tick}  snapshots={col.snapshots} missed={col.missed_ticks}")
        else:
            time.sleep(args.poll)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["step", "live"])
    p.add_argument("--url", default="http://localhost:8000")
    p.add_argument("--out", type=Path, default=None, help="output folder (default simulator/dataset/<timestamp>)")
    p.add_argument("--ticks", type=int, default=960, help="step mode: ticks to advance (96 = 1 simulated day)")
    p.add_argument("--reset", action="store_true", help="step mode: POST /admin/reset first (wipes the simulator!)")
    p.add_argument("--leave-paused", action="store_true", help="step mode: don't resume the clock afterwards")
    p.add_argument("--duration", type=float, default=300, help="live mode: wall-clock seconds to record")
    p.add_argument("--poll", type=float, default=0.03, help="live mode: seconds between tick checks")
    p.add_argument("--backfill", action="store_true", help="also pull older demand history (~666 ticks back)")
    p.add_argument("--no-admin", action="store_true", help="skip /admin/audit and /admin/faults")
    args = p.parse_args()

    out = args.out or Path(__file__).parent / "dataset" / datetime.now().strftime("%Y%m%d-%H%M%S")
    client = SimClient(args.url)
    health = client.get("/v1/health")
    print(f"simulator {health['status']}, {health['simulation']}; writing to {out}")

    col = Collector(client, out, with_admin=not args.no_admin)
    started = time.monotonic()
    try:
        col.collect_static()
        if args.backfill:
            col.backfill_history()
        (run_step if args.mode == "step" else run_live)(args, client, col)
    except KeyboardInterrupt:
        print("interrupted, saving what we have")
    finally:
        col.close()
    print(f"done in {time.monotonic() - started:.1f}s: {col.snapshots} snapshots, "
          f"{len(col.seen_history)} demand rows, {len(col.seen_audit)} audit rows, "
          f"missed {col.missed_ticks} tick snapshots -> {out}")


if __name__ == "__main__":
    main()
