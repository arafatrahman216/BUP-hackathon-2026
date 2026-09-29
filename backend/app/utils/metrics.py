"""Prometheus metrics (scraped at `GET /metrics`) plus a rolling window of recent requests,
so `GET /status` can report p95 latency and error rate without querying Prometheus."""

import math
import time
from collections import deque
from threading import Lock

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, PlatformCollector, ProcessCollector

REGISTRY = CollectorRegistry()
ProcessCollector(registry=REGISTRY)  # process_cpu_seconds_total, process_resident_memory_bytes (resource usage)
PlatformCollector(registry=REGISTRY)

HTTP_REQUESTS = Counter("http_requests_total", "HTTP requests handled", ["method", "route", "status"],
                        registry=REGISTRY)
HTTP_LATENCY = Histogram("http_request_duration_seconds", "HTTP request latency", ["route"], registry=REGISTRY,
                         buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
COMPONENT_HEALTH = Gauge("component_health", "1 healthy, 0.5 degraded, 0 down", ["component"], registry=REGISTRY)
SIMULATOR_LATENCY = Gauge("simulator_last_latency_seconds", "Latency of the last simulator call", registry=REGISTRY)
DATABASE_LATENCY = Gauge("database_ping_seconds", "Latency of SELECT 1", registry=REGISTRY)
PIPELINE_RUNS = Gauge("pipeline_runs", "Pipeline runs since start", registry=REGISTRY)
PIPELINE_TICK = Gauge("pipeline_last_processed_tick", "Last simulator tick processed", registry=REGISTRY)
PIPELINE_RUN_SECONDS = Gauge("pipeline_last_run_seconds", "Duration of the last pipeline run", registry=REGISTRY)

WINDOW_SECONDS = 300.0


class RequestWindow:
    """(time, seconds, is_error) of the requests in the last WINDOW_SECONDS."""

    def __init__(self, window: float = WINDOW_SECONDS, max_items: int = 50_000) -> None:
        self.window = window
        self._items: deque[tuple[float, float, bool]] = deque(maxlen=max_items)
        self._lock = Lock()

    def add(self, seconds: float, is_error: bool) -> None:
        with self._lock:
            self._items.append((time.monotonic(), seconds, is_error))

    def summary(self) -> dict:
        cutoff = time.monotonic() - self.window
        with self._lock:
            while self._items and self._items[0][0] < cutoff:
                self._items.popleft()
            items = list(self._items)
        if not items:
            return {"requests": 0, "p95_latency_ms": None, "error_rate": 0.0, "window_seconds": int(self.window)}
        durations = sorted(d for _, d, _ in items)
        p95 = durations[max(0, math.ceil(0.95 * len(durations)) - 1)]
        errors = sum(1 for *_, e in items if e)
        return {"requests": len(items), "p95_latency_ms": round(p95 * 1000, 1),
                "error_rate": round(errors / len(items), 4), "window_seconds": int(self.window)}


request_window = RequestWindow()
