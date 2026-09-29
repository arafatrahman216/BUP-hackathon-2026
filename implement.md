# Implementation Plan: Fuel Supply Operations Platform

Status: **DRAFT, waiting for confirmation of the open questions in §3.**
Sources: [problemset/problem.md](problemset/problem.md) (challenge brief) and
`problemset/BUP_Fuel_Supply_Simulator_Integration_Guide_Final.pdf` (simulator API).

Work through the steps in order. Each step lists **what** to build and **how**.
Finish each step with a checked **Done when** line and passing `pytest`.

---

## 1. What we are building (one paragraph)

We are building a decision-support platform on top of the BUP Fuel Supply Simulator. It runs this loop:
**observe** the simulated network (REST + SSE), **predict** station demand and stockout time,
**detect** risk and anomalies, **decide** allocations with an LP optimizer (greedy fallback),
**act**, either automatically for safe, confident decisions or after operator approval for the rest,
**explain** each decision with the LLM, and **monitor/recover** through built-in metrics, health checks,
retries, a circuit breaker and cached state. Operators use it through a lean React dashboard.

## 2. Confirmed decisions

| # | Topic | Decision |
|---|---|---|
| D1 | Operator UI | **Lean React dashboard** in the existing `frontend/` (reverses design.md's "backend-only" rule, because the brief requires an operator interface) |
| D2 | Intelligence core | **Forecast + optimizer**: hour-of-day seasonal demand forecast → stockout ETA → LP allocator (scipy HiGHS), with a greedy heuristic as fallback. Plus demand-anomaly detection |
| D3 | Autonomy | **Hybrid**: auto-dispatch low-risk, high-confidence recommendations; queue the rest for operator approval; an autopilot on/off toggle |
| D4 | Database | **Local Postgres container** in compose (no Supabase needed to run) |
| D5 | Observability | **Built-in only**: our own `/metrics` + health endpoints (psutil for CPU/mem), charted in the dashboard. No Prometheus/Grafana |
| D6 | Load testing | **k6** (Docker container) |
| D7 | Ports | Simulator **8000**, backend **8080**, frontend **5173**, Postgres **5432** |
| D8 | LLM role | Recommendation explanations, incident summaries, operator Q&A assistant (all with non-LLM fallbacks) |
| D9 | Auth | **None**: documented as an assumption (simulation only, local deployment) |
| D10 | CI/CD | **GitHub Actions**: lint, tests, frontend build, image build, compose smoke test |

## 3. Open questions (need your answer before or during the build)

| # | Question | My suggestion |
|---|---|---|
| Q1 | **Simulation speed.** With the default `SIMULATION_SPEED=8`, 8 ticks pass per second (= 2 simulated hours per second). A 2-tick shipment arrives in 0.25 s, so humans can't approve anything in time. What should the demo speed be? | Run the demo at `SIMULATION_SPEED=1` (or lower, if the image accepts floats like `0.5`), and use `/admin/step` in tests. Our decision cycle runs every N ticks (config), not on every tick. |
| Q2 | **Decision cycle trigger**: SSE `simulation.tick` events, REST polling, or both? | Both: the SSE tick triggers a refresh; a polling loop (every 2 s) is the fallback when SSE is down (`stream_disconnect` fault). |
| Q3 | **Hybrid thresholds**: when is a recommendation "safe" to auto-dispatch? | Auto only if: forecast confidence ≥ 0.7, the snapshot is not stale, no anomaly on that station, and quantity ≤ route.max_shipment. Everything else goes to review. |
| Q4 | **Decision horizon**: how far ahead does the optimizer plan? | 24 ticks (6 simulated hours). Covers the longest route (4 ticks) plus a safety buffer. |
| Q5 | **Frontend auth scaffold**: the template has `AuthProvider`/`useAuth`. Remove it, since D9 is no auth? | Remove it to keep things simple. |
| Q6 | **Supabase code**: keep `StorageRepository` and the Supabase URL builder (unused), or strip them? | Keep them (harmless); set `DATABASE_URL` for local Postgres. |

---

## 4. Architecture

```
                         ┌──────────────────────── our docker compose ────────────────────────┐
┌───────────────┐  REST  │ ┌──────────────────────── backend :8080 (FastAPI) ────────────────┐ │
│ BUP simulator │◄──────►│ │ SimulatorClient (timeouts, retry, circuit breaker, validation)  │ │
│   :8000       │  SSE   │ │        │                                                         │ │
│ /v1/*  /admin │───────►│ │ SyncWorker ──► StateCache (latest snapshot, stale flag)         │ │
└───────────────┘        │ │        │                                                         │ │
                         │ │ DecisionCycle: Forecaster → RiskDetector → Optimizer/Greedy     │ │
                         │ │        → Policy (auto | review) → Dispatcher → Audit            │ │
                         │ │ LLM (explain / incidents / Q&A)  ── template fallback           │ │
                         │ │ Metrics + Health + JSON logs                                     │ │
                         │ └──────────────┬──────────────────────────────────────────────────┘ │
                         │                │ SQLAlchemy          ▲ REST (poll 2–5 s)            │
                         │         ┌──────▼─────┐        ┌──────┴───────┐     ┌──────────┐     │
                         │         │ Postgres   │        │ React :5173  │     │ k6 (opt) │     │
                         │         └────────────┘        └──────────────┘     └──────────┘     │
                         └──────────────────────────────────────────────────────────────────────┘
```

The backend is the **only** thing that talks to the simulator. The frontend talks only to the backend.

---

## 5. Step-by-step plan

### Step 0: Housekeeping and docs alignment
**What:** Make the repo match the confirmed decisions before writing features.
**How:**
1. `design.md`: replace "backend-only" with "backend + lean React operator dashboard". Add a §3.x for the new
   backend folders (`simulator/`, `intelligence/`, `workers/`), switch the DB section to local Postgres,
   and add decision-log rows for D1–D10.
2. `features.md`: add F1–F12 (the steps below) with status `todo`.
3. `CLAUDE.md`: drop the "don't build a frontend" rule; add "run `cd frontend && npm test`".
4. Update the `README.md` quick start.

**Done when:** the docs no longer contradict each other.

### Step 1: One-command stack (compose)
**What:** Root `docker-compose.yml` runs the simulator, Postgres, backend and frontend together.
**How:**
1. Add service `simulator` (image `asifmahmoud414/bup-fuel-supply-simulator:1.0.0`, port 8000, env from
   `simulator/docker-compose.yml`, healthcheck on `/v1/health`). Keep `simulator/docker-compose.yml` for
   running the simulator alone.
2. Add `postgres:16-alpine` with a named volume and a `pg_isready` healthcheck.
3. Backend: host port `8080:8000`, `depends_on` simulator + postgres (`condition: service_healthy`),
   `DATABASE_URL=postgresql+asyncpg://...@postgres:5432/fuel`, `SIMULATOR_BASE_URL=http://simulator:8000`.
4. Add a backend healthcheck on `/api/v1/health/live`.
5. Add a `k6` service under `profiles: [loadtest]` so it doesn't start by default.
6. New env vars in `config.py` + `.env.example`: `SIMULATOR_BASE_URL`, `SIMULATOR_TIMEOUT_S`,
   `SIMULATOR_MAX_RETRIES`, `SYNC_POLL_INTERVAL_S`, `DECISION_EVERY_N_TICKS`, `DECISION_HORIZON_TICKS`,
   `AUTOPILOT_ENABLED`, `AUTO_MIN_CONFIDENCE`, `CB_FAILURE_THRESHOLD`, `CB_RESET_S`.
7. Add `/api/v1/assistant` and `/api/v1/decisions` to `RATE_LIMIT_PATH_PREFIXES`.

**Done when:** `docker compose up --build` gives healthy containers, and `curl localhost:8080/api/v1/health` works.

### Step 2: Simulator client (integration + resilience core)
**What:** A typed, defensive client for every `/v1/*` endpoint in guide §10.
**How:** `backend/app/simulator/`
1. `schemas.py`: Pydantic models that mirror the guide (Instance, Region, Depot, Station, Route,
   SupplyArrival, Event, Allocation, DemandObservation, Metrics, AllocationRequest). Fuel/status
   fields are enums. Use `extra="ignore"`, but require the core fields: **an invalid response fails
   validation → `SimulatorBadResponseError` → alert** (brief §11 "Invalid simulator response").
2. `client.py`: `SimulatorClient` on a shared `httpx.AsyncClient`:
   - per-request timeout; retries with exponential backoff + jitter on 503 `FAULT_INJECTED`, timeouts
     and connection errors (GETs always; POST allocations only because the `idempotency_key` makes retries safe);
   - a **circuit breaker** (closed → open after N consecutive failures → half-open after `CB_RESET_S`);
   - read the `X-Simulator-Stale: true` header → return `stale=True` alongside the data;
   - parse both error shapes: `{"detail":{code,message}}` (domain 409/404) and `{"error":{code}}` (faults);
     map domain codes (`ROUTE_DISRUPTED`, `INSUFFICIENT_INVENTORY`, …) to a typed `AllocationRejected`;
   - always call `/v1/demand-history` with a `limit`.
3. `sse.py`: an SSE reader for `/v1/stream` (httpx streaming). Ignore `:` comments; don't treat the 15 s
   keepalive as a disconnect; on 503 or a dropped connection, back off and reconnect, then **force a full REST refresh**.
4. `admin.py`: a small client for `/admin/step|run|pause|reset|events|faults`, used by tests, demo scripts
   and an optional "Scenario control" panel.

**Done when:** unit tests (respx-mocked) cover retry, breaker open/half-open, stale header, both error
shapes and bad payload rejection.

### Step 3: State sync and cache
**What:** Keep a fresh, validated picture of the world, and serve it even when the simulator is down.
**How:**
1. `workers/sync_worker.py`: a background task started in the lifespan. It triggers on the SSE
   `simulation.tick` (or on the poll timer when SSE is down), then fetches instance, depots, stations,
   routes, supply-arrivals, events, allocations, metrics and recent demand-history in parallel (`asyncio.gather`).
2. `StateCache` (in memory): the latest `Snapshot{tick, sim_time, fetched_at, stale, source_ok, ...}`.
   When a fetch fails, keep the last good snapshot and set `degraded=True` (brief §11 "cached state / degraded mode").
3. Persist to Postgres (repositories per §3.6):
   - `demand_observations` (dedupe on simulator id): training data for the forecaster;
   - `snapshots` (tick, JSON blob): replay and "what changed" diffing;
   - `sim_events` mirror: to detect new, started and resolved events.
4. Endpoints: `GET /api/v1/network` (the snapshot, with `stale`/`degraded` flags),
   `GET /api/v1/network/stations/{id}`, `GET /api/v1/network/timeline`.

**Done when:** stopping the simulator container leaves `/network` serving the last snapshot with `degraded=true`.

### Step 4: Demand forecaster (Predict)
**What:** Per station × fuel demand forecast for the next H ticks, with a confidence score.
**How:** `intelligence/forecaster.py`
1. Model: `rate(station, fuel, hour_of_day)`, learned from demand history as an EWMA per hour-of-day bucket
   (this captures the profile's busy/off-peak factors). Multiply by the station's current `demand_multiplier`
   relative to the multiplier seen at learning time, which picks up demand spikes immediately.
2. Cold start: seed with the guide's §8.5/8.6 profile tables (documented as "prior from simulator docs").
3. Confidence = f(sample count in the bucket, recent residual CV). Low data or high error → low confidence.
4. Track accuracy: store each forecast for tick t, compare with actual demand when t arrives, keep a
   rolling **MAPE** per station/fuel, and expose it as a metric (brief §14 "prediction error").
5. Save the model version (`forecaster_version`) on every recommendation.

**Done when:** tests show the learned rates match the profile within tolerance on synthetic history, and MAPE is computed.

### Step 5: Risk and anomaly detection (Detect)
**What:** Turn the forecast plus inventory into shortage risk, and spot abnormal conditions.
**How:** `intelligence/risk.py`, `intelligence/anomaly.py`
1. **Projected inventory** per station/fuel over H ticks = current + in-transit arrivals (from our
   allocations' `expected_arrival_tick`) − forecast demand. **Stockout ETA** = first tick below 0.
   **Risk level:** CRITICAL (ETA ≤ shortest available route transit + 1), HIGH (≤ 8 ticks), MEDIUM (≤ H), OK.
2. **Stockout probability**: from the forecast variance (normal approximation) → the "risk 72% → 19%" numbers.
3. **Anomalies:** demand z-score vs forecast (catches spikes before we read events); depot inventory drop not
   explained by our allocations; supply arrivals that switch to `DELAYED` or shrink in quantity (shipment_delay /
   supply_shortfall); routes becoming `DISRUPTED`; stations in `OUTAGE`; depots `CONSTRAINED`.
4. **Alerts table** (`alerts`: severity, type, entity, message, tick, status open/acked/resolved), deduplicated
   by (type, entity), auto-resolved when the condition clears. Log a recovery event when an alert resolves.
5. **Incidents**: group co-occurring alerts (for example, a route disruption plus a demand spike = "combined crisis").

**Done when:** tests inject each of the six event types via mocked snapshots and get the right alerts.

### Step 6: Allocation optimizer + fallback (Decide)
**What:** Choose shipments that minimize projected unmet demand under every simulator constraint.
**How:** `intelligence/optimizer.py`, `intelligence/heuristic.py`
1. **LP (scipy `linprog`, HiGHS)**. Variables `x[route, fuel] ≥ 0` for AVAILABLE routes only, plus shortfall slack
   `s[station, fuel] ≥ 0`. Constraints (mirroring the guide's §5.2 validation order):
   - Σ from depot ≤ `dispatch_capacity_per_tick` − pending this tick;
   - Σ per depot/fuel ≤ depot inventory (minus a reserve to protect against future supply delays);
   - station inventory + in-transit + x ≤ station capacity (no `DESTINATION_CAPACITY_EXCEEDED`);
   - projected need over the horizon − x − s ≤ 0.
   Objective: min Σ w_risk·s + λ·transit_ticks·x (prefer short routes, weight critical stations higher).
2. Post-process: split any x > `max_shipment` into several allocations; drop tiny quantities (< 500 L).
3. **Greedy fallback** (`heuristic.py`): sort by stockout ETA; for each station, pick the shortest available route
   with inventory; ship min(need, route max, depot remaining dispatch). It is used when the LP fails, times out or
   is infeasible. It's toggleable for the demo ("ML/optimizer unavailable → fallback policy", brief §11), and we
   count activations as a metric.
4. **Impact estimate** per recommendation: stockout ETA and probability before and after, unmet liters avoided.
   Store the top 2 **alternatives** (other route/depot, or "wait for supply arrival X").

**Done when:** tests cover disrupted-route rerouting (Gazipur→Karnaphuli when Patiya→Karnaphuli is down),
dispatch capacity limits, the capacity cap and the fallback path.

### Step 7: Decision engine, hybrid autopilot, dispatch, audit (Act)
**What:** Turn optimizer output into recommendations, apply the policy, and send them to the simulator safely.
**How:** `services/decision_service.py`, `workers/decision_worker.py`
1. Every `DECISION_EVERY_N_TICKS`: build the snapshot → forecast → risk → optimize → create `recommendations` rows
   (station, fuel, qty, route, depot, signals, constraints, impact, alternatives, confidence, method=lp|greedy,
   model version, status).
2. **Policy (Q3):** `AUTO` when autopilot is on and confidence ≥ threshold, the data is not stale, and there is no
   anomaly on the entity; otherwise `PENDING_REVIEW` ("prediction confidence too low → human review", brief §11).
3. **Dispatcher:** `POST /v1/allocations` with a deterministic `idempotency_key = rec-{id}-{part}` (safe retries).
   Map 409 codes to recommendation status `REJECTED_BY_SIM` + reason, and re-plan next cycle. While the breaker is
   open, queue the recommendation as `DEFERRED` and re-validate it when the simulator recovers (it may be obsolete by then).
4. **Expiry:** a pending recommendation becomes `EXPIRED` after K ticks or when a newer plan replaces it.
5. Track our allocations by status (PENDING → IN_TRANSIT → ARRIVED/FAILED) from SSE `allocation.status_changed`
   plus a REST re-GET.
6. **Decision audit log** (`decision_log`): every create/auto/approve/reject/dispatch/fail/cancel, with actor
   (`system`/`operator`) and payload.
7. API: `GET /api/v1/recommendations?status=`, `GET /api/v1/recommendations/{id}` (full reasoning),
   `POST .../{id}/approve`, `POST .../{id}/reject`, `POST /api/v1/allocations/{id}/cancel`,
   `GET/PUT /api/v1/autopilot`, `POST /api/v1/decisions/run` (run a cycle now), `GET /api/v1/decisions/history`.

**Done when:** an end-to-end test with a mocked simulator runs recommend → auto → dispatch → arrived, and
recommend → review → approve → dispatch, with 409 and 503 paths covered.

### Step 8: LLM layer (Explain)
**What:** Human-readable reasoning, incident reports and Q&A. Each one degrades gracefully.
**How:** `services/explain_service.py`, `services/assistant_service.py` (use the existing `LLMClient`)
1. **Recommendation explanation:** a prompt with a structured JSON context (signals, constraints, impact,
   alternatives, confidence), rendered lazily on first view and cached in the DB. **Fallback:** a deterministic
   text template (like the ALERT block in brief §9). Always show which one was used.
2. **Incident summary:** when an incident opens or resolves, write "what happened / affected / our response /
   status" via `complete_json`. Fallback: a template.
3. **Operator Q&A:** `POST /api/v1/assistant/ask {question}` answers from a compact snapshot + alerts + recent
   decisions context. Grounded only (the prompt forbids inventing numbers). It is read-only: the assistant
   **cannot** dispatch.
4. Record LLM latency, provider used and fallback activations as metrics.

**Done when:** tests with the fake AI provider pass, and with all providers failing the template fallback is returned.

### Step 9: Observability and health (Monitor)
**What:** Built-in metrics and health (D5), covering the four layers in brief §14.
**How:** `services/metrics_service.py`, middleware hook
1. **Application:** a request-metrics middleware keeps a rolling window per route: count, error count, latencies
   → rate, error %, p50/p95/p99.
2. **System:** `psutil` process + host CPU %, RSS memory, open connections.
3. **Intelligence:** forecast MAPE, mean confidence, alerts raised per hour, decisions per cycle,
   auto-vs-review ratio, greedy-fallback activations, LLM fallback activations, simulator retries and breaker state,
   service level (from `/v1/metrics`).
4. **Domain KPI:** simulator `service_level` and `unmet_demand_liters` over time (the real measure of our decisions).
5. `GET /api/v1/metrics` (JSON), `GET /api/v1/metrics/history` (sampled every 10 s, in memory, for charts).
6. **Health:** `GET /api/v1/health` (aggregate) → components Backend, Database (SELECT 1), Simulator
   (`/v1/health` + breaker state), Sync worker (last success age), Forecaster, Decision engine (last cycle
   age/method), LLM (last result). Each one reports healthy / degraded / down. `/health/live` is a cheap liveness check.
7. **Logs:** JSON log lines with request_id and event type (`decision.*`, `integration.failure`,
   `fallback.activated`, `recovery`), for evidence.

**Done when:** metrics and health show up and reflect an injected `unavailable` fault within one poll interval.

### Step 10: Operator dashboard (React)
**What:** A lean UI with 4–5 pages that poll the backend every 2–5 s. Plain styling, charts with a small lib (Recharts).
**How:** `frontend/src/pages/…`
1. **Overview:** tick/sim-time/status bar, a stale/degraded banner, service-level KPI, and a station × fuel grid
   (inventory bar vs capacity, stockout ETA, risk colour), depot cards (inventory, dispatch used, status),
   routes list (available/disrupted), incoming supply timeline.
2. **Recommendations:** a pending review queue (Approve/Reject), auto-dispatched list, and a detail drawer with
   the brief §9 ALERT block, LLM explanation, signals, constraints, before/after risk, alternatives and confidence.
   An autopilot toggle.
3. **Alerts & Incidents:** open/resolved alerts, incident cards with LLM summaries, and simulator events.
4. **Decision history:** the audit log table plus allocation ledger statuses.
5. **System health:** the component status table, p95/error rate/RPS, CPU/mem charts, intelligence metrics,
   and fallback counters.
6. **Assistant:** a small chat panel (a side drawer is fine).
7. Remove the auth scaffold (Q5). `VITE_API_BASE_URL=http://localhost:8080/api/v1`.

**Done when:** a judge can follow the whole demo story (§7) from the UI alone.

### Step 11: Tests
**What:** Automated tests for the parts that matter.
**How:**
1. Backend pytest: the simulator client (respx), forecaster, risk, optimizer + greedy, decision policy, dispatcher
   error mapping, API endpoints (`client` fixture, SQLite), and LLM fallback.
2. An optional integration test against the real simulator image (marked `@pytest.mark.sim`, run in CI via a
   service container): reset → pause → step N → run cycle → assert the allocation was accepted.
3. Frontend vitest: render tests for the Overview and Recommendation detail with mocked API data.

**Done when:** `cd backend && .venv/bin/pytest` and `cd frontend && npm test` are green.

### Step 12: CI/CD (GitHub Actions)
**What:** `.github/workflows/ci.yml` on push/PR.
**How:** jobs:
1. `backend`: setup Python 3.12, install, lint (ruff), pytest.
2. `frontend`: Node, `npm ci`, lint, test, build.
3. `integration`: `docker compose up -d --build` → wait for health → curl `/api/v1/health` and `/api/v1/network`
   → run the `sim`-marked tests → `docker compose down`.
4. `images`: build the backend/frontend images tagged with the git SHA (build only; no registry push, per D10).

**Done when:** the pipeline passes on GitHub (Source → Build → Test → Package → Deploy → Health Check, brief §12).

### Step 13: Load testing (k6)
**What:** Measure at least one meaningful path (brief §17).
**How:** `loadtest/` with k6 scripts:
1. `dashboard.js`: `GET /network`, `/recommendations`, `/metrics` (the dashboard backend path), ramping VUs 1→50.
2. `decision.js`: `POST /decisions/run` (end-to-end: snapshot → forecast → optimize) at a constant arrival rate.
3. Run via `docker compose --profile loadtest run k6 run /scripts/dashboard.js`. Export a summary JSON.
4. Write `loadtest/RESULTS.md`: workload definition, avg/p50/p95/p99, throughput, error rate, concurrency, CPU/mem
   (from our `/metrics`), plus observations about where the system saturates (rate limiter, DB pool, simulator latency).

**Done when:** results are committed and the numbers are explained.

### Step 14: Crisis and failure demo scripts (Resilience evidence)
**What:** Repeatable scripts that trigger each brief §10/§11 scenario through `/admin/*`.
**How:** `scripts/scenarios/*.sh` (or a Python CLI), plus an optional "Scenario control" panel in the UI
(clearly labelled *simulation admin*):

| Script | Injects | We must show |
|---|---|---|
| `demand_spike.sh` | `demand_spike` Dhaka ×1.8 | Anomaly alert → forecast adapts → more allocation to Mirpur/Tongi |
| `shipment_delay.sh` | `shipment_delay` Gazipur +8 ticks | Supply-delay alert → depot reserve logic → rebalanced plan |
| `depot_constraint.sh` | `depot_constraint` Patiya | Constraint alert → shift to Gazipur cross-region routes |
| `route_disruption.sh` | `route_disruption` patiya-karnaphuli | Reroute via gazipur-karnaphuli |
| `combined.sh` | spike + disruption + shortfall | Incident grouping + LLM incident report |
| `fault_unavailable.sh` | fault `unavailable` 60 s | Breaker opens → degraded banner, cached state → recovery |
| `fault_error_rate.sh` | fault `error_rate` 0.5 | Retries succeed; retry metric rises |
| `fault_stale.sh` | fault `stale_data` | Stale banner; autopilot pauses auto-dispatch |
| `fault_stream.sh` | fault `stream_disconnect` | SSE → polling fallback |
| `kill_llm.sh` | bad AI keys / provider down | Template explanations, fallback counter |
| `force_greedy.sh` | disable the optimizer flag | Greedy policy in use, marked in the UI |

**Done when:** each script runs and its "we must show" item is visible in the UI and metrics.

### Step 15: Documentation and demo prep
**What:** The required deliverables (brief §19).
**How:**
1. `README.md`: overview, one-command run, ports, env config, how to run tests, load tests and scenarios.
2. `docs/architecture.md`: an architecture diagram (Mermaid: simulator → sync → intelligence → decision → app →
   monitoring) plus the data model.
3. `docs/assumptions.md`: simulation-only, no auth (D9), forecast priors taken from the guide's profile tables,
   reserve policy, thresholds, known limits.
4. `docs/demo.md`: the §7 script with exact commands.
5. Capture evidence: screenshots of health/metrics during faults, log excerpts, load-test results.

---

## 6. Proposed backend layout (added to design.md in Step 0)

```
backend/app/
├── simulator/        schemas.py, client.py (retry + breaker), sse.py, admin.py
├── intelligence/     forecaster.py, risk.py, anomaly.py, optimizer.py, heuristic.py
├── workers/          sync_worker.py, decision_worker.py, metrics_sampler.py
├── models/           demand_observation, snapshot, sim_event, alert, incident, recommendation, decision_log, forecast_record
├── repositories/     one per table
├── services/         network, forecast, risk, decision, explain, assistant, metrics, health
└── controllers/      network, recommendations, alerts, decisions, assistant, metrics, health, scenario
```

## 7. Demo story mapping (brief §22)

| # | Story beat | Shown by |
|---|---|---|
| 1–2 | Normal operations, dashboard | Overview page, service level ≈ 1.0 |
| 3–5 | Demand rises → risk → shortage predicted | `demand_spike.sh` → anomaly alert, stockout ETA drops, risk turns red |
| 6–7 | Recommendation, operator inspects it | Recommendations detail: ALERT block + LLM explanation + alternatives |
| 8 | Allocation is simulated | Approve → allocation PENDING → IN_TRANSIT → ARRIVED; ETA recovers |
| 9–10 | Crisis → system adapts | `combined.sh` → incident report, reroute, reserve adjustments |
| 11–13 | Failure injected → detected → fallback | `fault_unavailable.sh` → health red, degraded banner, cached state; `kill_llm.sh`/`force_greedy.sh` |
| 14 | Operations continue | Fault expires → breaker closes → recovery log → service level holds |

## 8. Deliverable checklist (brief §19)

| Deliverable | Step |
|---|---|
| Working application | 1–10 |
| Source repository + setup docs | 15 |
| Simulator integration | 2, 3, 7 |
| Intelligence component | 4, 5, 6, 8 |
| Operator interface | 10 |
| Architecture diagram | 15 |
| Deployment (reproducible) | 1, 12 |
| Observability evidence | 9, 15 |
| Resilience demonstration | 2, 3, 14 |
| Load-test evidence | 13 |
| Final demo | 7 (this doc), 15 |

## 9. Suggested priority if time runs short

1. **Must:** Steps 0–7, 9, 10 (a minimal Overview + Recommendations + Health), 14 (the three most important scripts).
2. **Should:** 8, 11, 13, 15.
3. **Could:** 12's integration job, the Assistant chat, the scenario control panel, simulation replay from `snapshots`.
