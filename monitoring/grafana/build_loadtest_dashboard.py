"""Builds dashboards/load-test.json (run: python3 monitoring/grafana/build_loadtest_dashboard.py).

Data comes from backend/scripts/load_test.py, which serves its metrics while it runs (Prometheus job
`loadtest`): live client-side counters and latency, and one `loadtest_step_*{scenario, concurrency}` gauge
set per finished step. Per-step panels use `last_over_time(...[$__range])`, so set the time range to cover
the run you want to see (the newest run in the range wins).
"""

import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}
panels: list[dict] = []
cursor = {"x": 0, "y": 0, "h": 0}


def place(panel: dict, w: int, h: int) -> None:
    if cursor["x"] + w > 24:
        cursor["x"], cursor["y"], cursor["h"] = 0, cursor["y"] + cursor["h"], 0
    panel.update(id=len(panels) + 1, gridPos={"x": cursor["x"], "y": cursor["y"], "w": w, "h": h})
    if panel.get("type") != "row":
        panel["datasource"] = DS
    cursor["x"] += w
    cursor["h"] = max(cursor["h"], h)
    panels.append(panel)


def row(title: str, **extra) -> None:
    cursor["x"], cursor["y"], cursor["h"] = 0, cursor["y"] + cursor["h"], 0
    place({"type": "row", "title": title, "collapsed": False, "panels": [], **extra}, 24, 1)
    cursor["x"], cursor["y"], cursor["h"] = 0, cursor["y"] + 1, 0


def q(expr: str, ref: str = "A", legend: str = "", instant: bool = False) -> dict:
    t = {"refId": ref, "datasource": DS, "expr": expr, "legendFormat": legend}
    if instant:
        t.update(instant=True, range=False, format="table")
    return t


def stat(title, expr, unit, desc, decimals=1, w=4):
    place({"type": "stat", "title": title, "description": desc, "targets": [q(expr)],
           "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "color": {"mode": "fixed", "fixedColor": "text"},
                                        "noValue": "no run in range"}, "overrides": []},
           "options": {"colorMode": "value", "graphMode": "none", "textMode": "value",
                       "reduceOptions": {"calcs": ["lastNotNull"]}}}, w, 4)


def series(title, targets, unit, desc, w=12, h=8, stack=False):
    custom = {"fillOpacity": 10, "lineWidth": 2, "spanNulls": False}
    if stack:
        custom["stacking"] = {"mode": "normal"}
    place({"type": "timeseries", "title": title, "description": desc, "targets": targets,
           "fieldConfig": {"defaults": {"unit": unit, "custom": custom}, "overrides": []},
           "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["max", "lastNotNull"]},
                       "tooltip": {"mode": "multi"}}}, w, h)


def to_number_and_sort():
    return [{"id": "convertFieldType", "options": {"conversions": [{"targetField": "concurrency",
                                                                    "destinationType": "number"}]}},
            {"id": "sortBy", "options": {"sort": [{"field": "concurrency"}]}}]


RANGE = "[$__range]"
RATE = "[$__rate_interval]"
SC = 'scenario=~"$scenario"'
last = lambda f, sel=SC: f"last_over_time(loadtest_step_{f}{{{sel}}}{RANGE})"
# one label left (concurrency), so the queries of a panel join into one row per concurrency level
step = lambda f: f'max by (concurrency) ({last(f, "scenario=\"$scenario\"")})'
CONC = {"matcher": {"id": "byName", "options": "concurrency"},
        "properties": [{"id": "unit", "value": "none"}, {"id": "decimals", "value": 0}, {"id": "displayName", "value": "clients"}]}

# --- summary -------------------------------------------------------------------------------------------------
row("Run summary  (over the selected time range)")
stat("Requests sent", f"sum(increase(loadtest_requests_total{RANGE}))", "short",
     "Every request the load tester sent in the time range, all scenarios.", 0)
stat("Peak throughput", f"max(max_over_time(loadtest_step_throughput_rps{RANGE}))", "reqps",
     "Best step of any scenario: requests per second over a whole 15 s step.")
stat("Best p95", f"min(min_over_time(loadtest_step_p95_ms{RANGE}))", "ms",
     "Lowest p95 of any step (usually 1 client on the dashboard read).")
stat("Worst p99", f"max(max_over_time(loadtest_step_p99_ms{RANGE}))", "ms",
     "Highest p99 of any step: the slow tail at the heaviest load (queued decision runs).", 0)
stat("Error rate", f'(sum(increase(loadtest_requests_total{{outcome="error"}}{RANGE})) or vector(0)) / '
     f"clamp_min(sum(increase(loadtest_requests_total{RANGE})), 1)", "percentunit",
     "5xx answers or dropped connections, as a share of all requests.", 2)
stat("Peak backend memory", f"max(max_over_time(loadtest_step_mem_max_mib{RANGE}))", "mbytes",
     "Largest backend container memory seen during any step (docker stats).", 0)

# --- live ------------------------------------------------------------------------------------------------------
row("Live, as the load tester sees it")
series("Concurrent clients", [q("loadtest_active_clients", legend="{{scenario}}")], "short",
       "How many clients each scenario runs right now. Each staircase is one scenario stepping through its levels.",
       w=8)
series("Throughput (client side)", [q(f"sum by (scenario) (rate(loadtest_requests_total{RATE}))", legend="{{scenario}}")],
       "reqps", "Answers per second the load tester receives, per scenario.", w=8)
series("Errors (client side)", [q(f'sum by (scenario) (rate(loadtest_requests_total{{outcome="error"}}{RATE}))',
                                  legend="{{scenario}}")], "reqps",
       "5xx answers and dropped connections per second. Empty means none.", w=8)
series("Latency percentiles (client side, all scenarios)", [
    q(f"histogram_quantile(0.50, sum by (le) (rate(loadtest_request_duration_seconds_bucket{RATE})))", "A", "p50"),
    q(f"histogram_quantile(0.95, sum by (le) (rate(loadtest_request_duration_seconds_bucket{RATE})))", "B", "p95"),
    q(f"histogram_quantile(0.99, sum by (le) (rate(loadtest_request_duration_seconds_bucket{RATE})))", "C", "p99")],
    "s", "Measured by the load tester, so it includes network and queueing time the server does not see.")
series("Backend CPU", [
    q(f'rate(process_cpu_seconds_total{{job="backend"}}{RATE})', "A", "CPU (1 = one core)"),
], "percentunit", "CPU of the backend process. Around 100% the single uvicorn process is saturated.", w=6)
series("Backend memory", [q('process_resident_memory_bytes{job="backend"}', "A", "RSS")], "bytes",
       "Resident memory of the backend process. Flat under load means no leak.", w=6)

# --- per scenario (row repeated for each value of $scenario) -------------------------------------------------
row("Results: $scenario", repeat="scenario")
place({"type": "barchart", "title": "Throughput by concurrency", "description":
       "Requests per second over each 15 s step. Where the bars stop growing, the backend is saturated.",
       "targets": [q(step("throughput_rps"), instant=True)],
       "transformations": [{"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True, "job": True,
                                                                             "instance": True, "scenario": True},
                                                           "renameByName": {"Value": "req/s"}}}] + to_number_and_sort(),
       "fieldConfig": {"defaults": {"unit": "reqps", "color": {"mode": "fixed", "fixedColor": "blue"},
                                    "custom": {"fillOpacity": 80, "lineWidth": 0}}, "overrides": [CONC]},
       "options": {"xField": "concurrency", "orientation": "vertical", "showValue": "always", "barWidth": 0.6,
                   "legend": {"showLegend": False}, "xTickLabelRotation": 0, "tooltip": {"mode": "single"}}},12, 9)
place({"type": "barchart", "title": "Latency by concurrency (log scale)", "description":
       "p50 = typical request, p95/p99 = the slow tail. The x axis is concurrent clients.",
       "targets": [q(step("p50_ms"), "A", instant=True),
                   q(step("p95_ms"), "B", instant=True),
                   q(step("p99_ms"), "C", instant=True)],
       "transformations": [{"id": "merge", "options": {}},
                           {"id": "organize", "options": {"excludeByName": {"Time": True, "__name__": True, "job": True,
                                                                             "instance": True, "scenario": True},
                                                           "renameByName": {"Value #A": "p50", "Value #B": "p95",
                                                                            "Value #C": "p99"}}}] + to_number_and_sort(),
       "fieldConfig": {"defaults": {"unit": "ms", "custom": {"fillOpacity": 80, "lineWidth": 0,
                                                             "scaleDistribution": {"type": "log", "log": 10}}},
                       "overrides": [
                           {"matcher": {"id": "byName", "options": n}, "properties": [
                               {"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
                           for n, c in (("p50", "blue"), ("p95", "orange"), ("p99", "green"))] + [CONC]},
       "options": {"xField": "concurrency", "orientation": "vertical", "showValue": "never", "barWidth": 0.8,
                   "groupWidth": 0.75, "legend": {"showLegend": True, "displayMode": "list", "placement": "bottom"},
                   "tooltip": {"mode": "multi"}}},12, 9)

COLS = [("throughput_rps", "req/s", "reqps", 1), ("avg_ms", "avg", "ms", 1), ("p50_ms", "p50", "ms", 1),
        ("p95_ms", "p95", "ms", 1), ("p99_ms", "p99", "ms", 1), ("max_ms", "max", "ms", 0),
        ("error_rate", "errors", "percentunit", 2), ("requests", "requests", "short", 0),
        ("cpu_avg_pct", "CPU avg", "percent", 0), ("mem_max_mib", "memory max", "mbytes", 0)]
refs = [chr(ord("A") + i) for i in range(len(COLS))]
place({"type": "table", "title": "Every step", "description":
       "One row per concurrency level. CPU is the backend container (100% = one core; the solver thread can add more).",
       "targets": [q(step(f), r, instant=True) for (f, *_), r in zip(COLS, refs)],
       "transformations": [{"id": "merge", "options": {}},
                           {"id": "organize", "options": {
                               "excludeByName": {"Time": True, "__name__": True, "job": True, "instance": True,
                                                 "scenario": True},
                               "renameByName": {f"Value #{r}": label for (_, label, *_), r in zip(COLS, refs)},
                               "indexByName": {"concurrency": 0, **{label: i + 1 for i, (_, label, *_) in enumerate(COLS)}}}}]
                          + to_number_and_sort(),
       "fieldConfig": {"defaults": {"custom": {"align": "right"}}, "overrides": [
           {"matcher": {"id": "byName", "options": label},
            "properties": [{"id": "unit", "value": unit}, {"id": "decimals", "value": dec}]}
           for _, label, unit, dec in COLS] + [
           {**CONC, "properties": CONC["properties"] + [{"id": "custom.align", "value": "left"}]}]},
       "options": {"showHeader": True, "cellHeight": "sm"}},24, 7)

dash = {
    "uid": "fuel-load-test", "title": "Fuel Ops - Load Test", "tags": ["fuel-ops", "load-test"],
    "description": "Results of backend/scripts/load_test.py. Set the time range to cover a run.",
    "timezone": "browser", "schemaVersion": 41, "version": 1, "refresh": "5s",
    "time": {"from": "now-30m", "to": "now"}, "panels": panels, "annotations": {"list": []},
    "templating": {"list": [{
        "name": "scenario", "label": "Scenario", "type": "query", "datasource": DS,
        "query": {"query": "label_values(loadtest_step_p95_ms, scenario)", "refId": "scenario"},
        "definition": "label_values(loadtest_step_p95_ms, scenario)", "refresh": 2, "sort": 0,
        "multi": True, "includeAll": True, "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
    }]},
    "links": [{"title": "System Status", "type": "link", "url": "/d/fuel-system-status", "icon": "dashboard"}],
}
out = Path(__file__).parent / "dashboards" / "load-test.json"
out.write_text(json.dumps(dash, indent=2) + "\n")
print(f"wrote {out} ({len(panels)} panels)")
