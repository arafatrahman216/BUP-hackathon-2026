"""Forecast benchmark on a collected dataset (intelligence-plan P1, choice "A + D").

Walk-forward: at every tick each method forecasts demand h ticks ahead using only the past.
Reports WAPE (sum |error| / sum actual) per horizon. Stdlib only.

    cd backend && .venv/bin/python scripts/bench_forecast.py ../simulator/dataset/<run>/
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pipeline.demand_model import DemandModel  # noqa: E402

HORIZONS = (1, 4, 24)


def main(folder: str) -> None:
    root = Path(folder)
    rows = list(csv.DictReader(open(root / "demand_history.csv")))
    stations = {}
    for r in csv.DictReader(open(root / "station_inventory.csv")):
        stations.setdefault(r["station_id"], {"id": r["station_id"], "demand_profile": r.get("demand_profile"),
                                              "region_id": r.get("region_id"), "demand_multiplier": 1.0})
    series: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    for r in rows:
        series[(r["station_id"], r["fuel_type"])][int(r["tick"])] = float(r["demand_liters"])
    ticks = sorted({int(r["tick"]) for r in rows})
    by_tick = defaultdict(list)
    for r in rows:
        by_tick[int(r["tick"])].append({**r, "tick": int(r["tick"])})

    methods = ("naive_last", "seasonal_naive_1d", "moving_avg_8", "ewma_hour_no_prior", "structural_ours")
    err = {(m, h, w): 0.0 for m in methods for h in HORIZONS for w in ("day1", "after")}
    act = dict(err)
    model = DemandModel()
    ewma: dict[tuple[str, str, int], float] = {}
    hour = lambda t: (t * 15 // 60) % 24  # noqa: E731  (dataset starts at 00:00, 15-min ticks)

    for t in ticks:
        for (s, f), ser in series.items():
            past = [ser[k] for k in range(max(0, t - 8), t) if k in ser]
            for h in HORIZONS:
                target = t + h - 1
                if target not in ser:
                    continue
                window = "day1" if t < 96 else "after"
                truth = ser[target]
                preds = {
                    "naive_last": ser.get(t - 1),
                    "seasonal_naive_1d": ser.get(target - 96),
                    "moving_avg_8": sum(past) / len(past) if past else None,
                    "ewma_hour_no_prior": ewma.get((s, f, hour(target))),
                    "structural_ours": model.rate(s, f, hour(target), 1.0),
                }
                for m, p in preds.items():
                    if p is not None:
                        err[(m, h, window)] += abs(truth - p)
                        act[(m, h, window)] += truth
        world = SimpleNamespace(stations=stations, tick_minutes=15, tick=t, events=[],
                                instance={"sim_time": f"2026-01-01T{hour(t):02d}:{(t * 15) % 60:02d}:00"},
                                history=by_tick[t])
        model.ingest(world)
        for r in by_tick[t]:
            key = (r["station_id"], r["fuel_type"], hour(t))
            d = float(r["demand_liters"])
            ewma[key] = d if key not in ewma else ewma[key] + 0.25 * (d - ewma[key])

    print(f"Walk-forward WAPE on {root.name} ({len(ticks)} ticks, {len(series)} series). "
          "'-' = the method has no forecast yet (cold start)\n")
    cols = [(h, w) for w in ("day1", "after") for h in HORIZONS]
    print("| Method | " + " | ".join(f"{'day 1' if w == 'day1' else 'day 2+'} h={h}" for h, w in cols) + " |")
    print("|---|" + "---|" * len(cols))
    for m in methods:
        cells = [f"{err[(m, h, w)] / act[(m, h, w)]:.1%}" if act[(m, h, w)] else "-" for h, w in cols]
        print(f"| {m} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "../simulator/dataset/20260929-095304")
