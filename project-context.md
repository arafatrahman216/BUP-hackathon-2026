# Project Context: BUP Fuel Supply Operations Platform

Context brief for coding agents working on this repo. It summarizes the challenge
(`problem.md`), the simulator (`BUP_Fuel_Supply_Simulator_Integration_Guide_Final.md`),
what we **verified by running the simulator**, the intended architecture, and the feature
list. Read `design.md` for code conventions; this file covers the domain.

---

## 1. The challenge in one paragraph

The organizers provide a simulated Bangladeshi fuel network (2 depots, 4 stations, 6 roads,
3 fuels, 15-minute ticks). The simulator only **executes** shipment orders and reports what
happened; it never predicts or decides. We build the brain: read the world, forecast
demand, predict stockouts, recommend shipments (depot → station over a road), explain
them, let a human operator approve them, send them to the simulator, and keep working
through crises and software failures. We also need an operator web interface, Docker
deployment, monitoring and health status, a load test, and a live demo. Judges care more
about a working, explainable, resilient system than about model accuracy.
Loop: **Observe → Detect → Predict → Decide → Simulate → Act → Monitor → Recover.**

Scoring weights: product/UX 20%, intelligence and decision quality 20%, architecture and
integration 15%, DevOps and engineering 15%, resilience 10%, observability and load testing 10%,
demo 10%.

---

## 2. The simulator

### Running it
```bash
cd simulator
SIMULATOR_START_MODE=paused docker compose up -d    # repo default is "running"
curl -s http://localhost:8000/v1/health
```
- Base URL is `http://localhost:8000`, Swagger is at `/docs`, and the admin console is at `/admin`.
- Env: `SIMULATION_SPEED` (ticks per wall-clock second while running, default 8, which is
  **one simulated day in about 12 s**; use about 1 for demos), `TICK_MINUTES` (default 15),
  `SIMULATOR_START_MODE` (`paused` | `running`).
- **Port clash:** the simulator uses 8000, the same as our backend's default. Run the backend on 8001.
- From inside the backend container, reach it via `http://host.docker.internal:8000`
  (already in `extra_hosts`) or the compose service name. Make it a setting
  (`SIMULATOR_BASE_URL`).

### Hard rules
- It is deterministic: same seed + same actions + same events ⇒ identical state.
- **REST is the source of truth.** The SSE stream is only a hint to re-read.
- **The only domain write is `POST /v1/allocations`** (plus cancel). Everything else under `/v1` is read-only.
- `/admin/*` is for testing and for judges (clock control, crises, faults). Our product should not depend on it.
- Don't modify the simulator. Never hard-code world numbers; read them from the API.

### The world (fixed structure)
| Depot | Region | Dispatch limit per tick | Capacity D/P/O | Start D/P/O |
|---|---|---|---|---|
| `depot-gazipur` | Dhaka | 12,000 | 90k / 70k / 45k | 60k / 45k / 26k |
| `depot-patiya` | Chattogram | 11,000 | 85k / 65k / 40k | 55k / 42k / 24k |

| Station | Region | Profile | Capacity D/P/O | Start D/P/O |
|---|---|---|---|---|
| `station-mirpur` | Dhaka | urban_high | 15k / 14k / 9k | 9k / 9k / 5k |
| `station-tongi` | Dhaka | industrial | 18k / 9k / 6k | 11k / 6k / 3.5k |
| `station-karnaphuli` | Chattogram | highway | 14k / 15k / 9k | 8.5k / 9.5k / 5.2k |
| `station-coxsbazar` | Chattogram | regional | 12k / 12k / 7k | 7.5k / 7.5k / 4.2k |

| Route | Transit (ticks) | Max per shipment |
|---|---|---|
| `route-gazipur-mirpur` | 2 | 7,000 |
| `route-gazipur-tongi` | 2 | 6,500 |
| `route-patiya-karnaphuli` | 2 | 7,000 |
| `route-patiya-coxsbazar` | 3 | 6,000 |
| `route-gazipur-karnaphuli` (backup) | 4 | 5,000 |
| `route-patiya-mirpur` (backup) | 4 | 5,000 |

Region demand factors: Dhaka 1.00, Chattogram 1.08.

**Demand per day (liters)** and busy-hour factors:
| Profile | D / P / O | Noise | Busy hours → factor | Otherwise |
|---|---|---|---|---|
| urban_high | 8,500 / 10,500 / 5,600 | 0.10 | 07–09, 16–20 → 1.45 | 0.70 |
| industrial | 14,000 / 4,500 / 2,200 | 0.08 | 06:00–17:59 → 1.55 | 0.45 |
| highway | 10,500 / 11,000 / 6,200 | 0.12 | 06–09, 16–20 → 1.35 | 0.75 |
| regional | 7,200 / 7,600 / 3,600 | 0.10 | 07:00–20:59 → 1.25 | 0.65 |

Per-tick demand ≈ `daily / 96 × hour_factor × region_factor × demand_multiplier × noise`.
Verified: Mirpur petrol at night ≈ 10,500/96 × 0.70 ≈ 76 L per tick (observed 72–83).

Supply: 22 scheduled ship arrivals **to depots**. Four arrive in an initial burst at ticks
12–20, then 18 more every 64 ticks.

### Time
- `tick` is a step counter. Each tick is `tick_minutes` (15) of simulated time. 96 ticks make one day.
- `sim_time` is the simulated clock, starting at `2026-01-01T00:00:00`. Tick 100 is `2026-01-02T01:00`.
- **The simulator drives the clock**, not us. When running, it ticks automatically. When paused, only
  `POST /admin/step` advances it. Always read `tick_minutes` from `/v1/instance`.

---

## 3. Read endpoints (our input)

| Endpoint | Content |
|---|---|
| `GET /v1/health` | Liveness. **Bypasses faults**, so it says "ok" even while `/v1/*` is failing |
| `GET /v1/instance` | `tick`, `sim_time`, `tick_minutes`, `status` (PAUSED/RUNNING), `seed` |
| `GET /v1/regions` | Regions with `demand_factor` |
| `GET /v1/depots[/{id}]` | `status` (OPEN/CONSTRAINED), `dispatch_capacity_per_tick`, `capacity{}`, `inventory{}` |
| `GET /v1/stations[/{id}]` | `status` (OPEN/OUTAGE), `demand_profile`, `demand_multiplier`, `capacity{}`, `inventory{}` |
| `GET /v1/routes` | `status` (AVAILABLE/DISRUPTED), `transit_ticks`, `max_shipment` |
| `GET /v1/supply-arrivals` | Ships to depots: `quantity`, `planned_tick`, `actual_tick`, `status` (SCHEDULED/DELAYED/ARRIVED) |
| `GET /v1/events` | Crises, id-desc: `type`, `start_tick`, `end_tick`, `status` (SCHEDULED/ACTIVE/RESOLVED), `parameters` |
| `GET /v1/allocations` | Our shipments, id-desc |
| `GET /v1/demand-history?station_id=&limit=` | Past demand, 12 rows per tick. `limit` is 1–2000, default 200. **Always pass a limit** |
| `GET /v1/metrics` | The score (see below) |
| `GET /v1/stream` | SSE: `simulation.tick`, `allocation.status_changed`, `inventory.updated` (depots), `simulator.notice` |

**Demand history row.** This is a record of the past, not a forecast:
```json
{"station_id":"station-mirpur","fuel_type":"PETROL","tick":100,"sim_time":"2026-01-02T01:00:00",
 "demand_liters":156,"served_liters":0,"unmet_liters":156}
```
Unmet demand appears to be **lost**, with no backlog carried into later ticks. Preventing stockouts is what counts.

**`demand_multiplier` vs demand history.** The multiplier is a **current setting** on the
station, normally 1.0. It changes **only** when a `demand_spike` starts (×multiplier) or
ends (÷multiplier), so overlapping spikes stack. The tick doesn't change it, and it doesn't
include the time-of-day pattern (that factor is hidden and only visible in the history).
A good forecast is the pattern learned from history × the current multiplier.

**Score (`/v1/metrics`):**
```json
{"served_demand_liters":81809,"unmet_demand_liters":11245,"service_level":0.879,
 "allocation_liters":0,"allocation_failures":0}
```
`service_level` = served / (served + unmet). This is the primary quality number; push it toward 1.0.

---

## 4. Write endpoint (our only action)

`POST /v1/allocations`:
```json
{"idempotency_key":"rec-42-tongi-diesel","source_depot_id":"depot-gazipur",
 "destination_station_id":"station-tongi","route_id":"route-gazipur-tongi",
 "fuel_type":"DIESEL","quantity":6000}
```
- 201 means accepted with status `PENDING`. The allocation lifecycle is `PENDING → IN_TRANSIT → ARRIVED`, or `FAILED`
  (its road was cut before departure) or `CANCELLED`.
- **Idempotency:** the same key with the same body returns the existing allocation (201, or possibly 200; handle both). The same key
  with a different body returns `409 IDEMPOTENCY_KEY_MISMATCH`. Keys are never freed, even after a cancel.
- Validation order (first failure wins; errors are `{"detail":{"code","message"}}`):
  `NOT_FOUND`(404) → `ROUTE_MISMATCH` → `DEPOT_CLOSED` → `STATION_CLOSED` → `ROUTE_DISRUPTED`
  → `ROUTE_CAPACITY_EXCEEDED` → `INSUFFICIENT_INVENTORY` → `DISPATCH_CAPACITY_EXCEEDED`
  (this depot's pending plus in-flight this tick + qty > dispatch limit) → `DESTINATION_CAPACITY_EXCEEDED`
  (station inventory + qty > capacity). All of these are 409 except the 404. Bad enums or a quantity ≤ 0 give 422.
- `POST /v1/allocations/{id}/cancel` works only while the allocation is `PENDING` and refunds the depot. Otherwise it returns `409 CANNOT_CANCEL`.
- **Verified rules (tests on 2026-09-29):**
  - The destination-capacity check ignores in-transit fuel. If a truck arrives to a tank that's too full, the extra is **silently lost**
    (the status is still `ARRIVED` and the depot is still debited; the audit log shows `received` < quantity).
  - Multiple allocations on the same route in the same tick are allowed.
  - Supply arriving at a full depot is capped at capacity, and the excess is lost.
  - `DISPATCH_CAPACITY_EXCEEDED` counts only allocations created **this tick**; the limit resets every tick.
  - An allocation created at tick T departs at T and arrives at T + `transit_ticks`.
- **Post only when needed**, not on every tick. Decide on every tick; post when
  ticks-until-empty < transit + safety margin. Don't post too early, or the tank won't have room. If
  several stations need fuel at once, spread shipments across ticks (dispatch limit) and serve the most urgent first.

---

## 5. Crises and faults (injected via `/admin`)

**The shipped baseline scenario never starts a crisis on its own.** Crises and faults
come from `POST /admin/events` and `POST /admin/faults`, called by us for testing or by the judges.
A judging image *could* include preloaded crises. Either way they appear in `GET /v1/events`, and
upcoming ones show as `SCHEDULED`, so poll events every tick and plan ahead.

| Crisis type | Params | Effect (**verified** where marked) |
|---|---|---|
| `demand_spike` | `multiplier`(1.5), `station_ids[]`, `region_ids[]` | ✔ Station `demand_multiplier` ×2 → Mirpur petrol went from 80 to 156 L per tick. Reverts at end |
| `route_disruption` | `route_ids[]` | ✔ Route becomes `DISRUPTED` → `409 ROUTE_DISRUPTED`. Pending shipments on it fail. The backup route worked (4 ticks instead of 2) |
| `station_outage` | `station_ids[]` | ✔ Station becomes `OUTAGE`: **served = 0, all demand counts as unmet**, inventory frozen, `409 STATION_CLOSED` |
| `depot_constraint` | `depot_ids[]` | ✔ **Only the status label changes to `CONSTRAINED`.** Dispatch limit and inventory are unchanged, and shipments still succeed. Treat it as a warning |
| `shipment_delay` | `delay_ticks`(2), `depot_ids[]`, `fuel_types[]` | ✔ Future arrivals' `planned_tick` += delay and status becomes `DELAYED`. **One-shot, never undone** |
| `supply_shortfall` | `factor`(0.5), `depot_ids[]`, `fuel_types[]` | ✔ **Every future** arrival for the filter is cut (Gazipur 18,000 → 9,000). **Permanent** |

Empty filter lists mean "apply to all". Body: `{"type","start_tick","duration_ticks","parameters"}`.

| Fault type | Effect on `/v1/*` (not `/admin`, not `/v1/health`) | Verified |
|---|---|---|
| `latency` | Adds `delay_ms` (default 500) to every request | |
| `unavailable` | 503 `{"error":{"code":"FAULT_INJECTED"}}`, while health still says ok | ✔ |
| `error_rate` | 503 with probability `rate` (default 0.25) | |
| `stale_data` | Header `X-Simulator-Stale: true` on GETs | ✔ |
| `stream_disconnect` | `/v1/stream` returns 503 (under `detail`, not `error`) | |

Body: `{"type","duration_seconds"(≤3600),"parameters"}`. Faults auto-expire. `POST /admin/faults/clear` clears them all.

Other admin endpoints: `run`, `pause`, `toggle`, `step`, `reset` (wipes everything back to tick 0; we must detect the
tick going backwards and resync), `GET /admin/audit`, `GET /admin/events`, `GET /admin/faults`.

---

## 6. What we observed in a test run (baseline, no actions)

| Time | Tongi diesel | Mirpur petrol | Gazipur depot diesel |
|---|---|---|---|
| 00:00 (tick 0) | 11,000 | 9,000 | 60,000 |
| 12:00 (tick 48) | 3,997 | 4,326 | refilled by ship |
| 16:15 (tick 65) | **empty** | ~1,866 by 18:00 | |
| 24:00 (tick 96) | 0 | **0** | **90,000 (full)** |

- Service level after one day with no action was **0.879** (11,245 L unmet).
  **Depots fill up while stations run dry.** The simulator never moves fuel from depots to
  stations by itself; that is our job.
- One shipment (6,000 L Gazipur → Tongi) was created at tick 96, departed at tick 96 and arrived at tick 98.
- Supply arriving at a full depot is probably wasted, which is another reason to move fuel out regularly.

A replayable walkthrough with example requests is in `simulator-walkthrough.md`.

---

## 7. Intended architecture

```
Simulator :8000 ──SSE tick + REST reads──► Backend worker loop (per tick)
      ▲                                     1. read world  2. save snapshot to DB
      │                                     3. forecast → stockout risk → detect anomalies
      │ POST /v1/allocations                4. build recommendations  5. cache latest state
      │ (after operator approval)           ▼
      └───────────────────────────── Backend API (FastAPI, :8001)
                                            ▲  dashboard / alerts / recommendations / approve / health / metrics
                                            │
                                     Web interface (browser; polls 1–2 s or gets pushed updates)
```
- **The browser never calls the simulator.** The backend owns all simulator access, the cache
  and the history, so the UI keeps working (marked stale) when the simulator is down.
- Tick detection: SSE `simulation.tick` as the primary path, and polling `/v1/instance` about once a second as the fallback.
  Always re-read REST after an event.
- Resilience: timeouts, retry with backoff, a circuit breaker, a last-good-state cache, stale flagging,
  input validation, a rule-based fallback planner, and a template explanation when the LLM is down.

---

## 8. Features to build

Core (priority): **1, 2, 4, 5, 7, 10, 13, 14, 16**.

1. **Simulator client**: a typed client for every endpoint, with timeouts, retries and backoff, a circuit breaker,
   response validation, stale-header detection, and handling for both error shapes (`detail` and `error`).
2. **Tick watcher**: SSE listener with a polling fallback. Triggers the per-tick pipeline and detects resets.
3. **Snapshots**: persist world state per tick (inventories, route and station status, events, metrics)
   for charts, audit, and a cached state to use during outages.
4. **Demand forecast**: per station and fuel for the next N ticks. Hour-of-day pattern from history
   × current `demand_multiplier`. Track and expose forecast error.
5. **Stockout warning**: ticks and hours until empty per station and fuel, counting in-transit shipments and
   upcoming supply. Risk level: safe, watch or urgent.
6. **Crisis and anomaly detection**: read events (active and scheduled), compare actual demand against the forecast,
   catch road, station and depot status changes and delayed or shrunk supply. Produce alerts.
7. **Shipment planner**: constrained allocation (urgency-first heuristic or LP) that respects all ten
   validation rules and the dispatch limit per tick, reroutes around cut roads, and plans for transit time.
   Includes a **rule-based fallback** policy.
8. **Impact preview**: before and after risk and unmet liters for each recommendation, plus alternatives with
   the reason each was rejected, and confidence. Low confidence means human review.
9. **Plain-language explanation**: the existing `LLMClient` explains recommendations and crises (it doesn't
   make the decisions), with a template fallback.
10. **Operator approval and dispatch**: approve, edit or reject, then POST with a deterministic idempotency key.
    Auto-send is optional for low-risk cases. Approval requires operator auth.
11. **Shipment tracking**: follow allocation statuses and ETAs, alert on `FAILED` and suggest a replacement, cancel while `PENDING`.
12. **Decision log**: recommendation, reasoning, operator action, what was sent, and the actual outcome.
13. **Degraded mode**: simulator down → serve cached state marked stale and keep retrying. Stale or invalid data →
    alert and don't act. Planner or LLM down → fallback. Visible in the UI.
14. **Health and status**: backend, DB, simulator, forecast, planner and LLM health, plus p95 latency and error rate.
15. **Metrics and monitoring**: Prometheus metrics (request rate, latency, errors, alerts, fallback activations,
    forecast error, service level) with a Grafana dashboard and structured logs of key actions.
16. **Operator web interface**: stations and depots with fuel levels and risk colors, alerts and crises, incoming
    ships, trucks in transit, pending recommendations with approve buttons, the decision log, score and health.
17. **Load test**: k6 or Locust against a meaningful path. Report avg, p50, p95 and p99 latency, throughput, error rate and concurrency.
18. **One-command launch and CI**: one compose file for simulator, backend, frontend and monitoring, plus GitHub Actions to run tests and build.

---

## 9. Open issues / to confirm with the human

- **Frontend conflict:** `design.md` and `CLAUDE.md` say "backend-only, no frontend", but the brief requires an
  operator interface, a `frontend/` folder exists, and `docker-compose.yml` still starts it. The human
  wants a web interface. **Update design.md before building frontend code.**
- The backend port must move off 8000 because of the simulator clash.
- `SIMULATION_SPEED=8` is too fast for a demo. Pick a demo speed (about 1).
- Exact judge scoring of decisions is unspecified. We assume `service_level` is the key number.
- `features.md` is still empty. Populate it from §8 in the template format.

---

## 10. Decisions and clarifications (from discussion with the human)

- **Intelligence (brief §7) is a menu, not a checklist.** Only one meaningful capability is
  required. We deliberately pick **one per category, chained together**, and skip the rest
  (no transport-delay prediction, no bottleneck detection, no reinforcement learning):
  | Category | Our pick |
  |---|---|
  | Prediction | Demand forecast → hours until empty (feature 4 + 5) |
  | Detection | Unusual demand: actual demand far above forecast, plus event and status changes (feature 6) |
  | Decision | Priority-based constrained shipment planner with a rule-based fallback (feature 7) |
  | Generative AI | Explanation of each recommendation and crisis (feature 9). **Not a standalone chatbot**; the brief explicitly says a chatbot isn't enough |
  Rationale: the brief says "complexity itself will not guarantee a higher score". A clear,
  working predict → detect → decide → explain chain demos best.
- **Human in the loop.** The system recommends and the operator approves (brief §9, §11, §24). An
  operator-controlled **auto mode** may send small, routine, high-confidence shipments without a click.
  Large, risky or low-confidence ones always wait for approval.
- **Service level is the proof, not the whole score.** It measures decision quality (part of the
  20% intelligence weight). The other 80% is UX, architecture, DevOps, resilience, observability and the demo.
  Forecasts, warnings and alerts must be **visible to the operator**, not only fed into the planner.
