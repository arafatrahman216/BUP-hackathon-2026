"""Load test for the backend (problem.md §17).

Closed-loop: N concurrent clients, each sends its next request as soon as the last one answers,
for DURATION seconds per step. Reports avg / p50 / p95 / p99 latency, throughput, error rate
and the backend container's CPU / memory (sampled with `docker stats`).

    backend/.venv/bin/python backend/scripts/load_test.py            # full run, ~5 min
    backend/.venv/bin/python backend/scripts/load_test.py --quick    # 5 s steps

Results: backend/scripts/load_results/<timestamp>.json and .md

While it runs, the script serves Prometheus metrics on :9105 (`--metrics-port`, 0 = off): live client-side
counters/latency plus one `loadtest_step_*` gauge set per finished step. Prometheus scrapes them (job
`loadtest`) and Grafana shows them on the "Fuel Ops - Load Test" dashboard.
"""

import argparse
import asyncio
import json
import statistics
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, start_http_server

REG = CollectorRegistry()
REQS = Counter("loadtest_requests_total", "Requests sent by the load tester", ["scenario", "outcome"], registry=REG)
LAT = Histogram("loadtest_request_duration_seconds", "Client-side latency", ["scenario"], registry=REG,
                buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20))
CLIENTS = Gauge("loadtest_active_clients", "Concurrent clients right now", ["scenario"], registry=REG)
RUN = Gauge("loadtest_run_info", "1 while a load test runs", ["started"], registry=REG)
STEP_FIELDS = {"throughput_rps": "req/s", "avg_ms": "ms", "p50_ms": "ms", "p95_ms": "ms", "p99_ms": "ms",
               "max_ms": "ms", "error_rate": "fraction", "requests": "count", "cpu_avg_pct": "%",
               "cpu_max_pct": "%", "mem_max_mib": "MiB"}
STEP = {f: Gauge(f"loadtest_step_{f}", f"Result of a finished step ({u})", ["scenario", "concurrency"], registry=REG)
        for f, u in STEP_FIELDS.items()}

SCENARIOS = [
    # (name, method, path, concurrency levels, what it exercises)
    ("dashboard", "GET", "/api/v1/dashboard", [1, 10, 50, 100, 200],
     "Dashboard backend: cached pipeline state serialized to JSON (what the operator UI polls)"),
    ("status", "GET", "/api/v1/status", [1, 10, 50, 100],
     "System status: DB ping + component health"),
    ("recommendations", "GET", "/api/v1/recommendations", [1, 10, 50, 100],
     "Decision log: paginated Postgres read"),
    ("pipeline_run", "POST", "/api/v1/pipeline/run", [1, 2, 5, 10],
     "End-to-end decision: read simulator -> validate -> detect -> predict -> MIP decide -> post"),
]


def pct(sorted_ms: list[float], q: float) -> float | None:
    if not sorted_ms:
        return None
    k = (len(sorted_ms) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(sorted_ms) - 1)
    return round(sorted_ms[lo] + (sorted_ms[hi] - sorted_ms[lo]) * (k - lo), 1)


class DockerSampler(threading.Thread):
    """Samples CPU % / memory of one container with `docker stats` while a step runs."""

    def __init__(self, container: str | None) -> None:
        super().__init__(daemon=True)
        self.container = container
        self.samples: list[tuple[float, float]] = []
        self._stop = threading.Event()

    def run(self) -> None:
        while self.container and not self._stop.is_set():
            try:
                out = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{.CPUPerc}};{{.MemUsage}}",
                                      self.container], capture_output=True, text=True, timeout=10).stdout.strip()
                cpu, mem = out.split(";")
                mem = mem.split("/")[0].strip()
                mib = float(mem[:-3]) * {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024}[mem[-3:]]
                self.samples.append((float(cpu.rstrip("%")), mib))
            except Exception:
                time.sleep(1)

    def stop(self) -> dict:
        self._stop.set()
        self.join(timeout=15)
        if not self.samples:
            return {"cpu_avg_pct": None, "cpu_max_pct": None, "mem_max_mib": None}
        cpus, mems = [c for c, _ in self.samples], [m for _, m in self.samples]
        return {"cpu_avg_pct": round(statistics.mean(cpus), 1), "cpu_max_pct": round(max(cpus), 1),
                "mem_max_mib": round(max(mems), 1)}


async def step(client: httpx.AsyncClient, name: str, method: str, path: str, concurrency: int, duration: float,
               container: str | None) -> dict:
    latencies: list[float] = []
    errors: dict[str, int] = {}
    deadline = time.perf_counter() + duration

    async def worker() -> None:
        while time.perf_counter() < deadline:
            started = time.perf_counter()
            try:
                res = await client.request(method, path)
                ok = res.status_code < 500
                key = None if ok else str(res.status_code)
            except httpx.HTTPError as exc:
                ok, key = False, type(exc).__name__
            seconds = time.perf_counter() - started
            latencies.append(seconds * 1000)
            LAT.labels(name).observe(seconds)
            REQS.labels(name, "ok" if ok else "error").inc()
            if not ok:
                errors[key] = errors.get(key, 0) + 1

    sampler = DockerSampler(container)
    sampler.start()
    started = time.perf_counter()
    CLIENTS.labels(name).set(concurrency)
    await asyncio.gather(*(worker() for _ in range(concurrency)))
    CLIENTS.labels(name).set(0)
    elapsed = time.perf_counter() - started
    resources = sampler.stop()
    ms = sorted(latencies)
    n, n_err = len(ms), sum(errors.values())
    return {"concurrency": concurrency, "requests": n, "seconds": round(elapsed, 1),
            "throughput_rps": round(n / elapsed, 1), "error_rate": round(n_err / n, 4) if n else None,
            "errors": errors, "avg_ms": round(statistics.mean(ms), 1) if ms else None,
            "p50_ms": pct(ms, 0.50), "p95_ms": pct(ms, 0.95), "p99_ms": pct(ms, 0.99),
            "max_ms": round(ms[-1], 1) if ms else None, **resources}


def markdown(results: dict) -> str:
    lines = [f"# Load test {results['started']}", "", f"Target: `{results['base_url']}`, "
             f"{results['duration_s']} s per step, closed loop (each client waits for its answer).", ""]
    for sc in results["scenarios"]:
        lines += [f"## {sc['name']}: `{sc['method']} {sc['path']}`", "", sc["what"], "",
                  "| Concurrency | Requests | Throughput (req/s) | Avg (ms) | p50 | p95 | p99 | Max | Error rate "
                  "| CPU avg / max (%) | Mem max (MiB) |",
                  "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for r in sc["steps"]:
            err = f"{r['error_rate'] * 100:.2f}%" + (f" {r['errors']}" if r["errors"] else "")
            lines.append(f"| {r['concurrency']} | {r['requests']} | {r['throughput_rps']} | {r['avg_ms']} | {r['p50_ms']} "
                         f"| {r['p95_ms']} | {r['p99_ms']} | {r['max_ms']} | {err} | {r['cpu_avg_pct']} / "
                         f"{r['cpu_max_pct']} | {r['mem_max_mib']} |")
        lines.append("")
    return "\n".join(lines)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8001")
    ap.add_argument("--duration", type=float, default=15.0)
    ap.add_argument("--quick", action="store_true", help="5 s steps")
    ap.add_argument("--container", default="hackathontemplate-backend-1", help="'' to skip docker stats")
    ap.add_argument("--only", nargs="*", help="scenario names")
    ap.add_argument("--metrics-port", type=int, default=9105, help="Prometheus metrics for Grafana; 0 = off")
    ap.add_argument("--linger", type=float, default=20.0, help="seconds to keep serving metrics after the run")
    args = ap.parse_args()
    duration = 5.0 if args.quick else args.duration
    results = {"started": datetime.now().isoformat(timespec="seconds"), "base_url": args.base_url,
               "duration_s": duration, "scenarios": []}
    if args.metrics_port:
        start_http_server(args.metrics_port, registry=REG)
        RUN.labels(results["started"]).set(1)
        print(f"metrics on :{args.metrics_port}/metrics (Grafana: Fuel Ops - Load Test)")
    limits = httpx.Limits(max_connections=500, max_keepalive_connections=500)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=60, limits=limits) as client:
        (await client.get("/api/v1/health")).raise_for_status()
        for name, method, path, levels, what in SCENARIOS:
            if args.only and name not in args.only:
                continue
            sc = {"name": name, "method": method, "path": path, "what": what, "steps": []}
            for c in levels:
                r = await step(client, name, method, path, c, duration, args.container or None)
                sc["steps"].append(r)
                for f in STEP_FIELDS:
                    if r.get(f) is not None:
                        STEP[f].labels(name, str(c)).set(r[f])
                print(f"{name:16} c={c:<4} {r['throughput_rps']:>7} req/s  avg {r['avg_ms']:>7} p50 {r['p50_ms']:>7} "
                      f"p95 {r['p95_ms']:>7} p99 {r['p99_ms']:>7} ms  err {r['error_rate']:.2%}  "
                      f"cpu {r['cpu_avg_pct']}%  mem {r['mem_max_mib']} MiB", flush=True)
                await asyncio.sleep(2)  # let the backend settle between steps
            results["scenarios"].append(sc)
    out = Path(__file__).parent / "load_results"
    out.mkdir(exist_ok=True)
    stem = out / datetime.now().strftime("%Y%m%d-%H%M%S")
    stem.with_suffix(".json").write_text(json.dumps(results, indent=2))
    stem.with_suffix(".md").write_text(markdown(results))
    print(f"\nwrote {stem}.json and {stem}.md")
    if args.metrics_port:
        RUN.labels(results["started"]).set(0)
        print(f"serving final metrics for {args.linger:.0f} s so Prometheus scrapes them")
        await asyncio.sleep(args.linger)


if __name__ == "__main__":
    asyncio.run(main())
