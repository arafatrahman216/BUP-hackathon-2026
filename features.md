# Features

This is the build list for the project. The human writes features here; the coding agent
reads this file (together with [design.md](design.md)) and implements them.

## How to use this file

**Human:** add a feature using the template below. Keep it short: what the user can do,
the rules that matter, and what "done" looks like. Leave blank anything you don't know yet.

**Coding agent:**
1. Read [design.md](design.md) first and follow its structure and conventions.
2. Build features whose status is `todo`, from top to bottom, unless told otherwise.
3. Follow design.md §3.6 (model → schema → repository → service → dependency →
   controller → register router). This project is backend-only; don't build frontend pages.
4. Add or update tests for what you build.
5. When a feature is done, set its status to `done` and list what you added under **Notes**
   (endpoints, tables).
6. If you make a new design decision (library, pattern, data model), record it in the
   decision log in design.md.
7. If something here is unclear or contradicts design.md, ask. Don't guess.

Status values: `todo` · `in-progress` · `done` · `blocked`

---



---

## Features

<!-- Add your features below this line -->

### Baseline tick pipeline (read → post)
**Status:** done
**What:** Every simulator tick: read → validate → save → detect → predict → decide → explain →
(important? operator approves/edits/rejects : auto) → post, with a fallback at every step.
Rules are hard-coded (no model, no optimization); the model/solution plugs in later.
**Notes:**
- Endpoints: `GET /dashboard`, `GET /stream` (SSE), `POST /pipeline/run`, `GET /snapshots`,
  `GET /recommendations`, `GET /recommendations/{id}`, `POST /recommendations/{id}/approve`, `POST /recommendations/{id}/reject`; `/health` now reports simulator + pipeline.
- Tables: `tick_snapshots`, `recommendations`.
- Code: `app/pipeline/`, `services/pipeline_service.py`, `services/recommendation_service.py`, `repositories/simulator_repository.py`. Swap stages in `app/pipeline/__init__.py`.
- Env: `SIMULATOR_*`, `PIPELINE_*`, `FORECAST_WINDOW_TICKS`, `SAFETY_TICKS`, `URGENT_MARGIN_TICKS`, `MIN_SHIPMENT_LITERS`, `DEPOT_RESERVE_LITERS`, `AUTO_POST_ENABLED`, `APPROVAL_TTL_TICKS`, `APPROVAL_MIN_SECONDS`, `SNAPSHOT_EVERY_TICKS`.
- Posting: every approved plan is re-fitted to the current world just before it is posted (`pipeline.decide.recheck`); dispatch-limit refusals retry next tick; idempotency keys use a random per-recommendation token, and lost answers are reconciled by key.
- Stale data: cautious mode (urgent only, shipments × `STALE_QUANTITY_FACTOR`, skip recent destinations); env `STALE_DATA_MODE`, `STALE_QUANTITY_FACTOR`. Dashboard shows `pipeline.cautious`.
- Not yet: shipment tracking/replacement (FAILED allocations), cancel, operator auth.

### Operator dashboard
**Status:** done
**What:** Live web page for the operator: simulator link and tick, score, pipeline stage health, station fuel
levels with risk, approval queue (approve / edit quantity / reject), alerts and blocked needs, depots, routes,
trucks, incoming ships and crises, decision log, stale banner.
**Notes:** `frontend/src/pages/Dashboard/`, `components/dashboard/`, `hooks/useDashboard.js` (SSE, polling fallback). Tests in `DashboardPage.test.jsx`.

### LLM explanations ("Ask AI" on actions)
**Status:** done
**What:** Every recommendation in the approval queue and the decision log has an "Ask AI" button: the operator picks a
suggested question (by the recommendation's status) or types one; the backend builds a JSON context from the pipeline's own
detect/predict output and the action's state, asks Gemini 3.8 Flash, stores and shows the answer with the data it used.
**Notes:**
- Endpoints: `GET /explain/recommendations/{id}`, `POST /explain/recommendations/{id}`, `POST /explain`, `POST /explain/context`, `GET /explain/profiles`.
- Table: `action_questions`. Code: `app/explainability/` (metrics, `profiles.json`, prompt), `services/explain_service.py`,
  `frontend/src/components/dashboard/AskPanel.jsx`. Decisions: [explainability.md](explainability.md).
- Env: `EXPLAIN_*`, `GEMINI_MODEL=gemini-3.8-flash`; `/api/v1/explain` in `RATE_LIMIT_PATH_PREFIXES`.
- Not yet: Ask AI on stations/depots/alerts in the UI (API supports it via `POST /explain`), LLM text in the pipeline's explain stage, streaming answers.

### Intelligence: detect, predict, decide (intelligence-plan.md §0.1)
**Status:** done
**Notes:**
- Detect (`pipeline/detect.py`, `Detector`): D1 status changes, crises with countdown, supply delay/shortfall vs first seen, failed trucks; D2 z-score (2+ ticks) + CUSUM on log(actual/forecast); D3 skipped ticks (stale/invalid/reset already in the service); D4 depot reconciliation + wasted fuel; D5 single-route stations; D6 dispatch bottleneck, overdue trucks; D7 incidents per region. Alerts carry `explained_by`, `since_tick`, `region_id`.
- Predict (`demand_model.py`, `twin.py`, `StructuralPredictor`): published-pattern prior + EWMA per station x fuel x hour, shape shared across fuels, multiplier divided out; deterministic simulator copy gives time until empty (vs naive), risk %, unserved and tank overflow in 6 h, order-by and refill-from ticks, confidence; network outlook (days of fuel left per fuel, rationing flag, depot overflow, "do nothing" numbers).
- Decide (`optimizer.py`): strategic LP (fair share per station when rationing) + tactical MIP-MPC (whole trucks, dispatch limit across fuels, road/station windows from crises, tank and depot overflow penalties, lexicographic weights); "wait: planned for tick N" for stations served later; with/without impact from the simulator copy on each plan. Fallback: `RulePlanner`.
- Dashboard payload: `incidents`, `outlook` (incl. `planner` status/ms/budgets, `wasted_liters_observed`).
- Settings: `PREDICTOR`, `PLANNER`, `FORECAST_HORIZON_TICKS`, `HISTORY_FETCH_ROWS`, `PLANNER_TIME_LIMIT_SECONDS`, `RATIONING_TRIGGER_DAYS`, `MIN_CONFIDENCE_AUTO`, `ANOMALY_*`.
- Benchmark: `backend/scripts/bench_forecast.py` (walk-forward WAPE). Tests: `tests/test_intelligence.py`.
- Not done: explain (deferred), daily-bucket strategic LP, 8-scenario test bench.

### System status, Prometheus + Grafana, load test
**Status:** done
**What:** Health of each component (Backend API, Database, Fuel Simulator, Prediction Service, Decision Engine),
p95 latency and error rate, as JSON and as Prometheus metrics with a Grafana dashboard; a repeatable load test.
**Notes:**
- Endpoints: `GET /status`, `GET /metrics`. Code: `middlewares/metrics.py`, `utils/metrics.py`, `services/status_service.py`,
  `controllers/status_controller.py`. Tests: `tests/test_status.py`.
- Compose: `prometheus` (:9090), `grafana` (:3000, dashboard "Fuel Ops - System Status"). Config in `monitoring/`.
- Load test: `backend/scripts/load_test.py`; results in `backend/scripts/load_results/`.
- Grafana `Fuel Ops - Load Test` dashboard: live client-side view + per-scenario results (throughput and latency by
  concurrency, table of every step). Filled by the load tester's own metrics (:9105, Prometheus job `loadtest`).

