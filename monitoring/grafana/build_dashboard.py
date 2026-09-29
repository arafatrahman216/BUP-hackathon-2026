"""Builds dashboards/system-status.json (run: python3 monitoring/grafana/build_dashboard.py)."""

import json
from pathlib import Path

DS = {"type": "prometheus", "uid": "prometheus"}
panels, y = [], 0


def add(panel, w, h):
    global y
    x = sum(p["gridPos"]["w"] for p in panels if p["gridPos"]["y"] == y)
    if x + w > 24:
        y += max(p["gridPos"]["h"] for p in panels if p["gridPos"]["y"] == y)
        x = 0
    panel.update(id=len(panels) + 1, datasource=DS, gridPos={"x": x, "y": y, "w": w, "h": h})
    panels.append(panel)


def row(title):
    global y
    if panels:
        y = max(p["gridPos"]["y"] + p["gridPos"]["h"] for p in panels)
    panels.append({"id": len(panels) + 1, "type": "row", "title": title, "collapsed": False,
                   "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}, "panels": []})
    y += 1


def target(expr, legend="", ref="A"):
    return {"refId": ref, "datasource": DS, "expr": expr, "legendFormat": legend}


HEALTH_MAP = [{"type": "value", "options": {
    "1": {"text": "Healthy", "color": "green", "index": 0},
    "0.5": {"text": "Degraded", "color": "orange", "index": 1},
    "0": {"text": "Down", "color": "red", "index": 2}}},
    {"type": "special", "options": {"match": "null", "result": {"text": "No data", "color": "gray", "index": 3}}}]


def health(label, component, desc):
    add({"type": "stat", "title": label, "description": desc,
         "targets": [target(f'component_health{{component="{component}"}}')],
         "fieldConfig": {"defaults": {"mappings": HEALTH_MAP, "color": {"mode": "thresholds"},
                                      "thresholds": {"mode": "absolute", "steps": [
                                          {"color": "red", "value": None}, {"color": "orange", "value": 0.5},
                                          {"color": "green", "value": 1}]}}, "overrides": []},
         "options": {"colorMode": "background", "graphMode": "none", "textMode": "value",
                     "reduceOptions": {"calcs": ["lastNotNull"]}}}, 5 if component != "decision" else 4, 4)


def stat(title, expr, unit, desc, steps, decimals=1, w=6):
    add({"type": "stat", "title": title, "description": desc, "targets": [target(expr)],
         "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "color": {"mode": "thresholds"},
                                      "thresholds": {"mode": "absolute", "steps": steps}}, "overrides": []},
         "options": {"colorMode": "value", "graphMode": "area", "reduceOptions": {"calcs": ["lastNotNull"]}}}, w, 4)


def series(title, targets, unit, desc, w=12, h=8):
    add({"type": "timeseries", "title": title, "description": desc, "targets": targets,
         "fieldConfig": {"defaults": {"unit": unit, "custom": {"fillOpacity": 10, "lineWidth": 2}}, "overrides": []},
         "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["mean", "max", "lastNotNull"]},
                     "tooltip": {"mode": "multi"}}}, w, h)


G, O, R = "green", "orange", "red"
RATE = "[$__rate_interval]"
LAT = lambda q: f"histogram_quantile({q}, sum by (le) (rate(http_request_duration_seconds_bucket{RATE})))"

row("System status  (1 = Healthy, 0.5 = Degraded, 0 = Down; refreshed on every scrape)")
health("Backend API", "backend_api", "Degraded when more than 5% of requests in the last 5 min returned 5xx.")
health("Database", "database", "SELECT 1 on every scrape. Down when the query fails.")
health("Fuel Simulator", "simulator", "Healthy: connected over SSE, circuit closed, data fresh. Degraded: polling fallback, "
       "half-open circuit or X-Simulator-Stale data. Down: unreachable or circuit open.")
health("Prediction Service", "prediction", "Worst of the pipeline's detect + predict stages on the last run: ok = Healthy, "
       "fallback/skipped = Degraded, error = Down.")
health("Decision Engine", "decision", "Worst of the pipeline's decide + post stages on the last run (skipped while "
       "the simulator data is stale or invalid).")

stat("p95 latency", LAT(0.95), "s", "95% of API requests finished faster than this (histogram estimate over the rate window; "
     "SSE /stream and /metrics excluded).", [{"color": G, "value": None}, {"color": O, "value": 0.25}, {"color": R, "value": 1}], 3)
stat("Error rate", f'(sum(rate(http_requests_total{{status=~"5.."}}{RATE})) or vector(0)) / clamp_min(sum(rate(http_requests_total{RATE})), 1e-9)',
     "percentunit", "Share of requests answered with a 5xx. 4xx (bad input, rate limits) are client errors and not counted.",
     [{"color": G, "value": None}, {"color": O, "value": 0.01}, {"color": R, "value": 0.05}], 2)
stat("Throughput", f"sum(rate(http_requests_total{RATE}))", "reqps", "Requests per second handled by the backend.",
     [{"color": G, "value": None}], 1)
stat("Backend CPU", f"rate(process_cpu_seconds_total{RATE})", "percentunit",
     "CPU used by the backend process (1 = 100% of one core; uvicorn runs one Python process, so ~100% is its ceiling).",
     [{"color": G, "value": None}, {"color": O, "value": 0.7}, {"color": R, "value": 0.95}], 0)

row("Traffic and latency")
series("Throughput by route", [target(f"sum by (route) (rate(http_requests_total{RATE}))", "{{route}}")], "reqps",
       "Requests per second, split by route template.")
series("Latency percentiles (all routes)", [target(LAT(0.5), "p50", "A"), target(LAT(0.95), "p95", "B"),
                                            target(LAT(0.99), "p99", "C"),
                                            target(f"sum(rate(http_request_duration_seconds_sum{RATE})) / sum(rate(http_request_duration_seconds_count{RATE}))", "average", "D")],
       "s", "p50 = typical request, p95/p99 = the slow tail. A rising tail with flat p50 means queueing under load.")
series("p95 latency by route", [target(f"histogram_quantile(0.95, sum by (le, route) (rate(http_request_duration_seconds_bucket{RATE})))", "{{route}}")],
       "s", "Which endpoint is slow.")
series("Responses by status", [target(f"sum by (status) (rate(http_requests_total{RATE}))", "{{status}}")], "reqps",
       "2xx ok, 4xx client errors (422 validation, 429 rate limit), 5xx server errors.")

row("Resources, pipeline and simulator")
series("Backend CPU", [target(f"rate(process_cpu_seconds_total{RATE})", "cpu")], "percentunit",
       "Share of one core used by the backend process.", w=8)
series("Backend memory (RSS)", [target("process_resident_memory_bytes", "rss")], "bytes",
       "Resident memory of the backend process.", w=8)
series("Pipeline run duration", [target("pipeline_last_run_seconds", "last run")], "s",
       "How long the last read -> post pipeline run took (one run per simulator tick).", w=8)
series("Simulator & database latency", [target("simulator_last_latency_seconds", "simulator (last call)", "A"),
                                        target("database_ping_seconds", "database SELECT 1", "B")], "s",
       "Latency of the dependencies the backend waits on.", w=12)
series("Pipeline progress", [target("pipeline_last_processed_tick", "last processed tick", "A")], "none",
       "Simulator tick the pipeline last processed. A flat line while the simulator runs means the pipeline is stuck.", w=12)

dash = {"uid": "fuel-system-status", "title": "Fuel Ops - System Status", "tags": ["fuel-ops"], "timezone": "browser",
        "schemaVersion": 41, "version": 1, "refresh": "5s", "time": {"from": "now-15m", "to": "now"},
        "panels": panels, "templating": {"list": []}, "annotations": {"list": []}}
out = Path(__file__).parent / "dashboards" / "system-status.json"
out.write_text(json.dumps(dash, indent=2) + "\n")
print(f"wrote {out} ({len(panels)} panels)")
