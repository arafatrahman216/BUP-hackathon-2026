# Design

This is the single source of truth for how this project is built. It covers what lives
in each folder, the conventions to follow, and a log of design decisions.
**Coding agents: read this before writing code, and add to the decision log whenever you
make a new design choice.**

Feature requirements live in [features.md](features.md).

---

## 1. Stack

| Layer    | Choice |
|----------|--------|
| Backend  | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) |
| Database | Local Postgres 16 container (`db` in docker-compose, via `asyncpg`); Supabase Postgres still possible |
| Files    | Supabase Storage (REST API via `httpx`), as a repository with no routes |
| AI       | Gemini, Groq, OmniRoute behind one `LLMClient` with an env-configured fallback chain |
| Frontend | React 19 + Vite operator dashboard (`frontend/`), live via the backend's SSE |
| Simulator | BUP Fuel Supply Simulator on :8000 (separate compose in `simulator/`); backend on :8001 |
| Run      | Docker + Docker Compose (hot reload) |
| Monitoring | Prometheus (`prometheus-client`, scrapes `/api/v1/metrics`) + Grafana "System Status" dashboard (`monitoring/`) |

## 2. Repository layout

```
.
├── backend/              FastAPI app (see §3)
├── frontend/             operator dashboard (React + Vite, see §8)
├── simulator/            simulator compose file + dataset collector
├── monitoring/           Prometheus scrape config + Grafana provisioning and dashboard (see §9)
├── slide/                presentation material
├── docker-compose.yml    runs the backend
├── explainability.md     decisions behind the AI explanations (Ask AI)
├── design.md             this file
├── features.md           feature list the agent builds from
└── CLAUDE.md             entry point for Claude Code (points here)
```

The backend owns all simulator access; the browser only talks to the backend.
Routes: `GET /health`, the `/ai` endpoints, the pipeline/dashboard endpoints,
`/recommendations` (see §7a), `/explain` (see §7b), and `GET /status` + `GET /metrics` (see §9).

## 3. Backend

### 3.1 Folder by folder (`backend/app/`)

| Folder / file | What it holds | Rules |
|---|---|---|
| `main.py` | `create_app()`: middlewares, routers, lifespan (create tables, build the AI client, close HTTP clients). | Keep it thin. |
| `core/config.py` | `Settings` (pydantic-settings). **Every** env var is declared here. Also builds the Supabase DB URL. | Never read `os.environ` elsewhere; use `get_settings()`. |
| `core/database.py` | Async engine, `SessionLocal`, `get_db` dependency, `init_db()` (`create_all`). | |
| `core/exceptions.py` | `AppException` and its subclasses (`BadRequestError`, `UnauthorizedError`, `ForbiddenError`, `NotFoundError`, `ConflictError`, `ExternalServiceError`, `ServiceUnavailableError`). | Services raise these; never return error dicts by hand. |
| `core/dependencies.py` | Wiring: `get_<x>_service` builds a service with its repositories and clients. Annotated types `DbSession`, `LLM` (AI client), `Storage` (Supabase Storage). | One `get_<feature>_service` per feature. |
| `controllers/` | FastAPI routers (HTTP layer only). Now: `health_controller.py`, `ai_controller.py`, `pipeline_controller.py` (dashboard, SSE stream, manual run, snapshots), `recommendation_controller.py` (list, approve/edit, reject), `explain_controller.py` (catalog, context preview, free question, Ask AI per recommendation), `status_controller.py` (`/status` JSON, `/metrics` Prometheus). `__init__.py` registers every router into `api_router`. | Parse input, call one service method, return. No business logic, no DB access. |
| `services/` | Business logic. Now: `ai_service.py`, `pipeline_service.py` (one pipeline pass per tick), `recommendation_service.py` (approval + posting), `dashboard_service.py` (cached state + SSE), `explain_service.py` (pipeline snapshot → metrics → LLM → stored Q&A), `status_service.py` (component health, p95, error rate; refreshes the Prometheus gauges). One `<name>_service.py` with a `<Name>Service` class per feature. | No FastAPI imports (except `UploadFile`); raise `AppException`s. |
| `repositories/` | Data access. Now: `storage_repository.py` (Supabase Storage), `simulator_repository.py` (simulator `/v1` client: timeout, retry + backoff, circuit breaker, stale-header detection, both error shapes), `snapshot_repository.py`, `recommendation_repository.py`, `action_question_repository.py`. One `<name>_repository.py` per table. | The only layer that touches the DB session, the storage API or the simulator. |
| `models/` | SQLAlchemy ORM: `base.py` has `Base` and `TimestampMixin` (`created_at`, `updated_at`); `snapshot.py`, `recommendation.py`, `action_question.py` (Q&A per recommendation). | Import every new model in `models/__init__.py`, or its table won't be created. |
| `schemas/` | Pydantic request/response models. Now: `common.py` (`ErrorResponse`, generic `Page[T]`), `ai.py`, `pipeline.py`, `recommendation.py`, `explain.py`. Per resource: `<Name>Create`, `<Name>Update`, `<Name>Read`. | Always set a `response_model`; never return ORM objects raw. |
| `middlewares/` | `cors.py`, `metrics.py` (request count + latency per route template), `request_logging.py`, `error_handler.py`, `rate_limiter.py`, and `setup_middlewares()` in `__init__.py`. | See §3.3. |
| `utils/` | `logger.py` (logging with request ids), `pagination.py` (`page_params` dependency + `build_page` → `Page[T]`), `metrics.py` (Prometheus registry + 5-min request window). | Framework-agnostic helpers. |
| `ai/` | Provider-agnostic LLM module (see §4). | |
| `explainability/` | LLM explanations (see §7b): `types.py` (`Subject`, `Snapshot`, `MetricContext`), `metrics.py` (`@metric` registry + built-in metrics over the pipeline's World/Forecast/Alert), `profiles.json` (**which metrics each question type sends to the LLM, params, suggested questions**), `context.py` (load profiles, build the JSON context), `prompt.py` (system prompt + messages). | Metrics are pure (no I/O) and never recompute detect/predict; `ExplainService` does the I/O. |
| `pipeline/` | Tick pipeline stages (see §7a): `types.py` (World, Forecast, Plan, Alert), `validate.py`, `detect.py` (stateful `Detector`, D1-D7), `demand_model.py` (structural demand model), `twin.py` (deterministic simulator copy + network outlook), `predict.py` (`StructuralPredictor`; baseline `MovingAveragePredictor`), `optimizer.py` (strategic LP + tactical MIP-MPC), `decide.py` (`RulePlanner` baseline/fallback, approval reasons), `explain.py`, `state.py` (in-memory cache + SSE broadcaster), `watcher.py` (SSE listener + polling fallback), `__init__.py` (stage builders: **swap in a model here**). | Stages are pure (no I/O); `PipelineService` does the I/O. |

`backend/tests/`: pytest suite with fake AI providers, a mocked Supabase Storage API, and
a throwaway SQLite database. Run it with `cd backend && .venv/bin/pytest`.

### 3.2 Request flow

```
HTTP → CORS → Metrics → RequestLogging → CatchAllError → RateLimit → controller
     → service → repository → Supabase (Postgres / Storage)
                → LLMClient → provider chain
```

### 3.3 Middlewares and the error contract

- **CORS**: origins from `CORS_ORIGINS` (comma-separated). Exposes `X-Request-ID`, `Retry-After`, `X-RateLimit-*`.
- **Request logging**: assigns a request id (or reuses the incoming `X-Request-ID`), logs `METHOD path -> status (ms)`, and returns `X-Request-ID`. Every log line includes the id.
- **Error handler**: every error response has **one shape**:
  ```json
  {"success": false,
   "error": {"code": "NOT_FOUND", "message": "Order 3 not found", "details": null, "request_id": "a1b2c3"}}
  ```
  | Source | Status / code |
  |---|---|
  | `AppException` subclasses | their own status / code |
  | Validation errors | 422 `VALIDATION_ERROR`, `details = [{field, message, type}]` |
  | DB `IntegrityError` | 409 `CONFLICT` |
  | AI chain exhausted | 502 `AI_PROVIDERS_FAILED`, `details = attempts[]` |
  | Unknown AI provider | 400 `AI_UNKNOWN_PROVIDER` |
  | Invalid JSON from the model | 502 `AI_BAD_RESPONSE` |
  | Storage not configured / failed | 503 `STORAGE_NOT_CONFIGURED` / 502 `STORAGE_ERROR` |
  | Rate limit | 429 `RATE_LIMITED` + `Retry-After` |
  | Anything else | 500 `INTERNAL_ERROR` (exception text in `details` only when `DEBUG=true`) |
- **Rate limiter**: in-memory sliding window per client IP. It applies only to paths starting with `RATE_LIMIT_PATH_PREFIXES` (default `/api/v1/ai`) and only to non-GET requests. A feature route outside `/ai` that calls the LLM is **not** limited unless you add its prefix.

Successful responses are the plain resource (no envelope). Paginated lists use `Page[T]`:
`{items, total, page, page_size, pages}`.

### 3.4 Database (local Postgres)

- **Default:** the `db` service in `docker-compose.yml` (`postgres:16-alpine`, data in the `pgdata` volume).
  Compose sets the backend's `DATABASE_URL` to `postgresql+asyncpg://fuel:fuel@db:5432/fuel`, overriding
  `backend/.env`. Credentials/port come from `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` /
  `POSTGRES_PORT` (defaults `fuel` / `fuel` / `fuel` / `5432`).
- Backend on the host (uvicorn outside Docker): `docker compose up -d db`, and `backend/.env` has
  `DATABASE_URL=postgresql+asyncpg://fuel:fuel@localhost:5432/fuel`.
- **Supabase (optional):** leave `DATABASE_URL` empty and the URL is built from `SUPABASE_URL` + `SUPABASE_PASSWORD`
  (`SUPABASE_POOLER_HOST` set → session pooler as `postgres.<ref>`, IPv4; empty → direct `db.<ref>.supabase.co`, IPv6-only).
- Tests use SQLite (`DATABASE_URL=sqlite+aiosqlite:///...`).
- `DB_COMMAND_TIMEOUT_SECONDS` (default 10) is asyncpg's query timeout: a query on a dead connection fails instead of
  hanging forever. `pool_recycle=300` replaces idle connections. Pool is 5 + 5 overflow.
- Tables are created on startup with `Base.metadata.create_all`. There are no migrations, so changing an existing column
  means altering it by hand (`docker compose exec db psql -U fuel -d fuel`) or dropping the table in dev
  (`docker compose down -v` wipes the whole database).
- Repositories commit their own writes: `add`/`setattr` → `await session.commit()` → `await session.refresh(obj)`. For multi-step atomic work, `flush()` in the repository and commit once in the service.

### 3.5 File storage (Supabase Storage)

`StorageRepository` talks to `SUPABASE_URL/storage/v1` with the service-role key and the
`SUPABASE_BUCKET_NAME` bucket. It has **no routes**. When a feature needs uploads, inject
`Storage` into its service, sanitize file names there, reject `..`, and enforce
`MAX_UPLOAD_MB`. The bucket is public, so `public_url(path)` works. For private access,
use `create_signed_url(path, seconds)`.
**The service-role key bypasses Row Level Security and must never reach the frontend.**

### 3.6 Adding a backend feature (e.g. "orders")

```python
# models/order.py  (then add `from app.models.order import Order` to models/__init__.py)
class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))

# schemas/order.py
class OrderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)

class OrderRead(OrderCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime

# repositories/order_repository.py
class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, order_id: int) -> Order | None:
        return await self.session.get(Order, order_id)

    async def create(self, data: dict) -> Order:
        order = Order(**data)
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order

# services/order_service.py
class OrderService:
    def __init__(self, repo: OrderRepository) -> None:
        self.repo = repo

    async def get(self, order_id: int) -> Order:
        order = await self.repo.get(order_id)
        if order is None:
            raise NotFoundError(f"Order {order_id} not found")
        return order

# core/dependencies.py
def get_order_service(session: DbSession) -> OrderService:
    return OrderService(OrderRepository(session))

# controllers/order_controller.py  (then include_router in controllers/__init__.py)
router = APIRouter(prefix="/orders", tags=["orders"])
Service = Annotated[OrderService, Depends(get_order_service)]

@router.get("/{order_id}", response_model=OrderRead)
async def get_order(order_id: int, service: Service):
    return await service.get(order_id)
```

Then add `tests/test_orders.py` using the `client` fixture from `tests/conftest.py`.

## 4. AI module (`backend/app/ai/`)

| File | Purpose |
|---|---|
| `types.py` | `ChatMessage`, `LLMResponse` (`text`, `provider`, `model`, `usage`, `attempts`), `ProviderAttempt`, `TokenUsage` |
| `exceptions.py` | `ProviderError` (one provider failed), `AllProvidersFailedError`, `UnknownProviderError`, `AIResponseParseError` |
| `providers/base.py` | `BaseLLMProvider`: `from_settings()`, `is_configured`, `generate()`, shared HTTP/error handling |
| `providers/openai_compatible.py` | Generic `/chat/completions` provider |
| `providers/gemini.py`, `groq.py`, `omniroute.py` | Concrete providers (Gemini uses its REST `generateContent` API; Groq and OmniRoute are OpenAI-compatible) |
| `registry.py` | `@register_provider` and the name → class map |
| `client.py` | `LLMClient`: walks the chain with fallback. Helpers: `chat()`, `complete()`, `complete_json()`, `describe()` |
| `__init__.py` | `get_llm_client()` singleton (also a FastAPI dependency) |

HTTP endpoints: `GET /ai/providers`, `POST /ai/chat`, `POST /ai/generate`.

**Fallback configuration (env):**
- `AI_PROVIDER_ORDER=gemini,groq,omniroute`: tried left to right. Entries can repeat (`gemini,gemini,groq` retries Gemini once) and can pin a model (`groq:llama-3.1-8b-instant`).
- `AI_FALLBACK_ENABLED=false` → only the first entry is used.
- Providers without credentials are **skipped** (recorded as `skipped` in `attempts`).
- An unknown provider name in the chain fails at startup.
- Passing `provider=` (and optionally `model=`) to `chat()` bypasses the chain.

**Using AI in a feature service:** take the `LLM` dependency in `get_<x>_service` and pass it to the service, then:
```python
reply = await self.llm.complete("Summarize: ...", system="You are ...")   # reply.text
data  = await self.llm.complete_json('Return {"tags": [string]} for: ...')  # parsed JSON
```

**Adding a provider:**
- OpenAI-compatible (OpenAI, OpenRouter, Together, Mistral, Ollama…): subclass `OpenAICompatibleProvider` with `name` and `from_settings`, decorate it with `@register_provider`, add `<NAME>_API_KEY/_MODEL/_BASE_URL` to `Settings` and `.env.example`, and import the module in `providers/__init__.py`.
- Other APIs: subclass `BaseLLMProvider` and implement `generate()` (see `gemini.py`).

Not implemented yet: streaming responses, tool/function calling.

## 5. Configuration

- Backend: `backend/.env` (gitignored). The documented template is `backend/.env.example`, and every key is declared in `core/config.py`. Empty values fall back to the defaults.
- Docker Compose reads `backend/.env`. The port can be overridden with `BACKEND_PORT`.

## 6. Running

```bash
docker compose up --build        # db :5432, backend :8001 (docs at /docs), frontend :5173,
                                 # Prometheus :9090, Grafana :3000 (admin/admin, anonymous view on)

# or locally
docker compose up -d db          # local Postgres for a host-run backend
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --port 8001 --reload
.venv/bin/pytest
```

## 7a. Tick pipeline

```
read → validate → save → detect → predict → decide → explain
     → (important? operator approves/edits/rejects : auto) → post
```

- **When:** `TickWatcher` listens to the simulator's SSE (`simulation.tick`) and also polls
  `/v1/instance` every `PIPELINE_POLL_SECONDS` as the fallback. One worker runs the pipeline;
  triggers during a run are coalesced (a fast simulator makes us skip ticks, not queue them).
  A tick going backwards is a **reset**: open recommendations are expired and state resyncs.
- **Stages (baseline = hard-coded rules, no model):**
  - *read*: all `/v1` GETs in parallel + `demand-history` (limit = stations × fuels × window).
  - *validate*: inventories ≥ 0 and ≤ capacity, routes reference known depots/stations. Fatal → don't act.
    Stale header (`X-Simulator-Stale`) → **cautious mode** (`STALE_DATA_MODE=cautious`): plan `urgent` needs only,
    shipments × `STALE_QUANTITY_FACTOR` (floored to 100 L), skip station/fuels we posted to within one trip
    (max transit + 1), and every plan carries a "stale" reason (→ operator). `STALE_DATA_MODE=stop` → don't act.
  - *save*: compact `tick_snapshots` row every `SNAPSHOT_EVERY_TICKS`.
  - *detect*: alerts for outages, disrupted routes, constrained depots, active/scheduled crises, delayed ships, failed shipments, unmet demand.
  - *predict*: rate = mean demand of the last `FORECAST_WINDOW_TICKS`; cover = (inventory + incoming) / rate;
    risk `urgent` if cover < lead + `URGENT_MARGIN_TICKS`, `watch` if cover < lead + `SAFETY_TICKS`.
  - *decide*: for `watch`/`urgent` (lowest cover first), fastest AVAILABLE route; qty = min(free space after incoming,
    route max, depot stock − reserve, depot dispatch left this tick), floored to 100 L, ≥ `MIN_SHIPMENT_LITERS`.
    Skips station/fuels with an open recommendation. Unplannable needs are reported as `blocked`.
  - *important?* only real trade-offs: low confidence, rationing over fair share, backup route, depot not OPEN,
    an ACTIVE crisis touching the station/region/depot/route, stale data, or `AUTO_POST_ENABLED=false` →
    an urgent shipment taking more than `URGENT_REVIEW_DEPOT_SHARE` (50%) of the depot's stock of that fuel →
    `PENDING_APPROVAL`, **or stockout risk** (`REVIEW_RISK_ENABLED`, `ReviewRules`): tank ≤ `REVIEW_FILL_FRACTION` (50%) full
    and empty within `FORECAST_HORIZON_TICKS`, stockout probability ≥ `REVIEW_STOCKOUT_PROB` (30%), less than
    `REVIEW_EMPTY_MARGIN_TICKS` (4) between "empty" and the fastest truck landing, or demand still unserved with the
    shipment (simulator copy). Each reason carries its numbers. Otherwise `APPROVED` (auto); unanswered cards auto-approve
    at the dynamic deadline, which is capped so the tank never runs dry (below).
  - *explain*: template text.
  - *re-check* (right before every post, `pipeline.decide.recheck`): the plan is re-fitted to the current world with
    the planner's limits (free space after incoming, route max, depot stock − reserve, dispatch left). Auto plans and
    unedited approvals may grow or shrink; operator-edited quantities and stale data only shrink. A resize is appended
    to the explanation. Station closed / route cut / no room / no stock → `REFUSED` with the simulator's code, not sent;
    dispatch limit used up → stays `APPROVED`, retried next tick. After a post, the allocation is added to the cached
    world (and depot stock deducted) so later re-checks in the same tick see it.
  - *post*: `POST /v1/allocations` with key `bup-{token}-{station}-{fuel}-{qty}`. The random token is stored on the
    recommendation when it is created (never derived from the DB id); a new quantity keeps the token with a new
    suffix. Before posting, an allocation in `/v1/allocations` carrying the stored key (an earlier attempt whose answer
    was lost) marks the recommendation `POSTED` instead of sending again.
- **Fallbacks:** read fails → cached world marked stale, no action; invalid/stale data → no action; save fails → continue;
  predict fails → last known rates; decide fails → fallback planner; explain fails → template;
  post transient failure → stays `APPROVED`, retried next tick; `DISPATCH_CAPACITY_EXCEEDED` → retried next tick;
  other post 4xx → `REFUSED` + simulator code; stale data → cautious mode.
- **Never-dry deadline cap:** an unanswered card is auto-approved no later than the last wait `d` for which the
  simulator copy (current trucks, no new one) keeps the tank ≥ `DEADLINE_SAFETY_TICKS` × demand per tick through the
  truck's arrival at `d + transit`, i.e. the tank holds (wait + transit + safety) × demand per tick. When the cap binds
  there is no `MIN_REVIEW_SECONDS` hold; the card's `deadline` shows `limited_by` (`never_dry` | `loss` | `ttl`) and
  `must_keep_liters`.
- **Recommendation lifecycle:** `PENDING_APPROVAL → APPROVED → POSTED | REFUSED`, or `REJECTED`, or `EXPIRED`
  (older than `APPROVAL_TTL_TICKS` **and** `APPROVAL_MIN_SECONDS`, or a simulator reset).
- **Locks:** `state.run_lock` serializes runs; `state.lock` covers decide → post and operator approve/reject.
- **Endpoints:** `GET /dashboard`, `GET /stream` (SSE `state` events + `depot` hints), `POST /pipeline/run`,
  `GET /snapshots`, `GET /recommendations`, `GET /recommendations/{id}`, `POST /recommendations/{id}/approve`
  (`{quantity?, note?}`), `POST /recommendations/{id}/reject`.
- **Not built yet:** shipment tracking/replacement (FAILED allocations), cancel, operator auth. (LLM explanations: §7b; the explain stage still writes template text.)

## 7b. Explainability (`/explain`, "Ask AI")

Full rationale: [explainability.md](explainability.md).

```
Ask AI (approval card / decision-log row) → POST /explain/recommendations/{id} {question}
  → profile "recommendation" (profiles.json) → metric list
  → snapshot = pipeline cache (World + predict Forecasts + detect Alerts + blocked)
               | no cache yet → read_world() + build_predictor().predict() + detect() + stockout_alerts()
  + open recommendations (DB) + longer demand history for the station (simulator, optional)
  → each metric → one JSON block → {"_meta": {subject, stale_data, data_source, notes}, <metric>: ..., "_unavailable"}
  → system prompt + profile instructions + question + JSON → LLMClient (Gemini 3.8 Flash first) → answer
  → stored in `action_questions` (question, answer, model, tick, the exact context)
```

- **Same numbers as the pipeline:** `forecast`, `alerts`, `station_ranking`, `risk_rules` expose predict/detect output and
  the settings the pipeline decided with; metrics never re-implement them. Swapping the predictor in `app/pipeline/__init__.py`
  changes explanations too.
- **Change what the LLM sees:** edit `app/explainability/profiles.json` (metrics per profile, `params`, `suggested_questions`
  per recommendation status), or per request with `metrics` / `params`. Read on every request (no restart).
- **Add a metric:** `@metric("name")` in `metrics.py`, taking a `MetricContext`; return JSON or `None` (not applicable).
- **Degraded inputs** are stated in `_meta.notes` (live read, old action, missing long history, DB down); a raising metric is listed
  in `errors`/`_unavailable`. No cache and no simulator → 503 `SIMULATOR_UNAVAILABLE`. LLM errors use the AI codes (§3.3); nothing is stored then.
- **LLM:** `EXPLAIN_PROVIDER` empty → the `AI_PROVIDER_ORDER` chain (Gemini first, with fallback). `GEMINI_MODEL=gemini-3.8-flash`.
- **Endpoints:** `GET /explain/recommendations/{id}` (suggestions for its status + earlier Q&A), `POST /explain/recommendations/{id}`
  (`{question}` → stored Q&A), `POST /explain` (any question, not stored), `POST /explain/context` (the JSON only, no LLM),
  `GET /explain/profiles`. POSTs are rate limited (`/api/v1/explain` in `RATE_LIMIT_PATH_PREFIXES`).

## 8. Frontend (`frontend/src/`)

| Path | What it holds |
|---|---|
| `api/api.js` | The only HTTP module: `dashboardApi` (get, run, streamUrl), `recommendationsApi` (approve, reject), `explainApi` (questions, ask) |
| `hooks/useDashboard.js` | Live state: EventSource on `/stream`; polls `/dashboard` every 2 s while SSE is down |
| `pages/Dashboard/` | Operator page: status bar, score, pipeline stages, stations, approvals, alerts, depots, routes, trucks, ships/crises, decision log |
| `components/dashboard/` | `StationCard`/`FuelGauge`, `DepotCard`, `PipelineStrip`, `ApprovalCard`, `AskPanel` (Ask AI: suggestions, question, stored answers, data used), tables, `StatusBadge` |
| `utils/format.js` | Formatting + risk/status meta (icon + label + color; color never alone) |

## 9. Monitoring and load testing

- `GET /api/v1/status`: `{status, components: {backend_api, database, simulator, prediction, decision}, requests,
  p95_latency_ms, error_rate, window_seconds}`. Each component is `healthy | degraded | down`:
  API degraded when > 5% of requests in the last 5 min were 5xx; database = `SELECT 1`; simulator healthy on SSE with a
  closed circuit and fresh data, degraded on polling / half-open / stale, down when unreachable or open; prediction =
  worst of the last run's detect + predict stages, decision = decide + post (`ok` healthy, `fallback`/`skipped` degraded,
  `error` down). Overall = worst component.
- `GET /api/v1/metrics` (Prometheus text): `http_requests_total{method,route,status}`, `http_request_duration_seconds`
  (histogram per route template), `component_health{component}` (1 / 0.5 / 0), `simulator_last_latency_seconds`,
  `database_ping_seconds`, `pipeline_*`, `process_*` (CPU, RSS). `/stream` and `/metrics` are not counted.
- Grafana dashboard `monitoring/grafana/dashboards/system-status.json` is generated by
  `monitoring/grafana/build_dashboard.py` (edit the script, re-run, Grafana reloads the file).
- Load test: `backend/.venv/bin/python backend/scripts/load_test.py` (closed loop, per-endpoint concurrency steps,
  avg/p50/p95/p99, throughput, error rate, container CPU/memory) → `backend/scripts/load_results/`.
- Load-test dashboard `Fuel Ops - Load Test` (`dashboards/load-test.json`, built by `build_loadtest_dashboard.py`):
  while it runs, `load_test.py` serves Prometheus metrics on :9105 (job `loadtest`, reached via `host.docker.internal`):
  live `loadtest_requests_total` / `loadtest_request_duration_seconds` / `loadtest_active_clients`, and one
  `loadtest_step_*{scenario, concurrency}` gauge set per finished step. Per-step panels use `last_over_time(...[$__range])`,
  so the time range picks the run; one row per scenario (`$scenario` repeat).

## 7. Decision log

Add a row whenever a design choice is made. Newest at the bottom.

| Date | Area | Decision | Why |
|---|---|---|---|
| 2026-09-29 | Backend | Layered structure: controllers → services → repositories → models; schemas for I/O | Clear place for everything |
| 2026-09-29 | Backend | Async SQLAlchemy 2.0 + `create_all` on startup, no Alembic | Hackathon speed; add migrations if the schema stabilizes |
| 2026-09-29 | Backend | Repositories commit their own writes | Commit happens before the response is sent; simple mental model |
| 2026-09-29 | Backend | One JSON error shape for every error; successful responses are unwrapped | Clients handle errors in one place; OpenAPI stays accurate |
| 2026-09-29 | Backend | In-memory rate limiter on AI prefixes, counting non-GET requests only | Protects free-tier AI quotas; swap for Redis if running multiple instances |
| 2026-09-29 | AI | Direct REST calls via `httpx` instead of vendor SDKs | Fewer dependencies, one error-handling path, easy to add providers |
| 2026-09-29 | AI | Provider chain + fallback flag in env; repeats = retries; `provider:model` pins | User requirement: configurable fallback and order |
| 2026-09-29 | Database | **Supabase** Postgres, URL built from `SUPABASE_*` vars; session pooler because the direct host is IPv6-only | User requirement; must work from Docker |
| 2026-09-29 | Storage | Supabase Storage through `StorageRepository` (REST), service-role key server-side only, no routes by default | Ready for features that need uploads; keeps secrets off the client |
| 2026-09-29 | Template | **No demo resources** (no Items/Files APIs); only health + AI routes | User requirement: leftover demo files and routers could cause bugs in the real project |
| 2026-09-29 | DevOps | Docker Compose with source mounts + hot reload | One command to run everything |
| 2026-09-29 | Scope | **No frontend**: the project is backend-only | User decision for the BUP Fuel Supply Simulator challenge |
| 2026-09-29 | Intelligence | Detect: data/clock checks, state diffs + events, z-score + CUSUM on actual ÷ forecast, inventory reconciliation, single-route risk, incidents, bottlenecks (intelligence-plan.md §0.1) | Covers brief §7/§10/§11; rules are exact, CUSUM catches sustained spikes |
| 2026-09-29 | Intelligence | Demand forecast = one structural model (guide prior + EWMA per station × fuel × hour × live multiplier, shape shared across fuels); other models only as bench benchmarks | Demand formula is published and noise is ~2% over 6 h, so a mix/ensemble adds cost, not accuracy |
| 2026-09-29 | Intelligence | Stockout risk and impact from a deterministic copy of the simulator; risk % by normal approximation; Monte Carlo optional | One engine powers P2–P7; Monte Carlo barely changes results at this noise level |
| 2026-09-29 | Intelligence | Decide = strategic daily LP (rationing across days) + tactical MIP-MPC (6 h) with lexicographic goals (unserved → waste → balance → short roads); fallback priority greedy + reorder point | Fuel is finite after tick 212, so waste and cross-day distribution decide the score |
| 2026-09-29 | Data | `simulator/collect_dataset.py` (stdlib only) builds CSV datasets from every simulator GET endpoint; `step` mode (pause + `/admin/step`) is the default way to get gap-free, deterministic data; output in gitignored `simulator/dataset/` | `demand-history` only returns the newest 2,000 rows, so data must be pulled while the sim runs |
| 2026-09-29 | Scope | **Frontend added**: React operator dashboard in `frontend/` (supersedes "no frontend") | User request: operator must observe and approve |
| 2026-09-29 | Pipeline | Stages are pure functions/classes in `app/pipeline/`; `PipelineService` does the I/O; each stage has a fallback and reports ok/fallback/skipped/error | Model/solution can replace predictor/planner/explainer without touching I/O; resilience is visible |
| 2026-09-29 | Pipeline | Baseline rules only: moving-average rate, cover vs lead + safety, fastest available route, no optimization | User requirement: hard-coded rules; the model is integrated later |
| 2026-09-29 | Pipeline | "Important" = urgent risk, backup route, depot constrained, active crisis, or auto-post off → operator; else auto-post | User decision |
| 2026-09-29 | Pipeline | Tick detection: simulator SSE primary, `/v1/instance` polling fallback; triggers coalesced into one worker | REST is the source of truth; never queue behind a fast simulator |
| 2026-09-29 | Integration | Simulator client is a repository with timeout, retries + backoff, circuit breaker, stale-header flag | Only the repository layer does external I/O |
| 2026-09-29 | Data | Tables `tick_snapshots` (compact JSON per tick) and `recommendations` (proposal + operator action + post result) | Audit/charts + decision log; one row per recommendation |
| 2026-09-29 | Data | Pipeline writes are batched (flush + one commit per stage) | Supabase round-trips are ~100 ms; per-row commits made runs take seconds |
| 2026-09-29 | Pipeline | ~~Idempotency key `bup-rec-{id}-{station}-{fuel}-{qty}`~~ (superseded below) | Retries are safe; an operator edit changes the body, so it needs a new key |
| 2026-09-29 | Pipeline | Recommendations expire only when older than `APPROVAL_TTL_TICKS` **and** `APPROVAL_MIN_SECONDS` | At speed 8 a tick TTL alone expires them before a human can read them |
| 2026-09-29 | Frontend | Backend re-publishes its own SSE (`/stream`, full state per run); browser polls `/dashboard` as fallback | User decision; the browser never calls the simulator |
| 2026-09-29 | DevOps | Backend on host port 8001; `SIMULATOR_BASE_URL` defaults to `http://host.docker.internal:8000` in compose | Simulator owns :8000 |
| 2026-09-29 | Pipeline | Every post re-fits the plan to the current world first (supersedes posting approved plans as-is); dispatch-limit refusals wait a tick instead of `REFUSED` | Approvals can be hundreds of ticks old at speed 8; overflow on arrival is silently lost; the guide says the dispatch limit frees up next tick |
| 2026-09-29 | Pipeline | Idempotency key `bup-{random token}-{station}-{fuel}-{qty}`, token stored at creation; lost answers reconciled by key via `/v1/allocations` (supersedes `bup-rec-{id}-…`) | DB-id keys repeat after a DB reset while the simulator keeps its allocations (same body → silent no-op, different body → mismatch) |
| 2026-09-29 | Pipeline | Stale data → cautious mode (urgent only, ×0.5 shipments, skip recent destinations) instead of stopping; `STALE_DATA_MODE=stop` restores the old behaviour | A stale fault can last an hour; the simulator still validates every post against live state |
| 2026-09-29 | AI | Explainability is a standalone module (`app/explainability/`): pluggable `@metric` functions declare the simulator sources they need; `profiles.json` maps question types to metric lists; the service fetches only those sources and sends one JSON context to the LLM | User requirement: metrics and how they are computed must be easy to change later without touching the I/O or prompt code |
| 2026-09-29 | AI | Explanations read the simulator live instead of the pipeline cache; partial failures are reported in the context (`_unavailable`) rather than failing the request | Keeps the module independent of the pipeline; the LLM is told what data is missing |
| 2026-09-29 | AI | Explanations use the pipeline's cached World + Forecasts + Alerts (live read through the same `read_world`/predict/detect code when there is no cache) instead of their own simulator reads and calculations (supersedes "read the simulator live") | User requirement: detection and prediction already exist; answers must match what the system decided with |
| 2026-09-29 | AI | "Ask AI" per recommendation in the approval queue and decision log; every Q&A is stored in `action_questions` with the exact context sent | Audit trail of what the operator was told and why; reload shows earlier answers |
| 2026-09-29 | AI | Default Gemini model `gemini-3.8-flash` | Best accuracy and latency of 2.5 Flash / 3.8 Flash / 3.1 Pro on six operator questions; not a preview |
| 2026-09-29 | AI | Suggested questions per recommendation status live in `profiles.json` | Tunable without code, next to the metrics they rely on |
| 2026-09-29 | Database | **Switched to a local Postgres 16 container** (`db` service, `pgdata` volume); Supabase Postgres kept as an option (empty `DATABASE_URL`); Supabase Storage unchanged | Supabase round-trips (~100 ms+) made pipeline runs take ~1.3 s, and a half-open pooler connection hung the pipeline and blocked approvals. Local: ~60 ms per run, ~60 ms per approval |
| 2026-09-29 | Database | asyncpg `command_timeout` (`DB_COMMAND_TIMEOUT_SECONDS`, 10 s) + `pool_recycle=300` | A dead connection must fail fast, never hang a run that holds the pipeline lock |
| 2026-09-29 | Intelligence | MIP/LP with **PuLP 2.x + HiGHS** (`highspy`), CBC as the backup solver; `PLANNER`/`PREDICTOR` settings pick optimizer/structural (default) or the rule baselines; the stateful demand model and detector live in `PipelineState` | PuLP 4 changed its API and dropped the bundled CBC; HiGHS solves the 6 h MIP in ~0.1-0.4 s |
| 2026-09-29 | Intelligence | Rationing is approved at the policy level: shipments within a station's fair-share budget auto-post; over-budget, low-confidence, urgent, backup-road or active-crisis shipments need the operator | User decision; per-shipment approval would make almost everything manual after tick 212 |
| 2026-09-29 | Intelligence | Strategic layer is a single-window LP (max-min fair coverage over the remaining days of fuel), not daily buckets yet | User decision to fit the 1-hour build; daily buckets are the next step |
| 2026-09-29 | Intelligence | MIP uses whole trucks (binary, min size) on every tick plus a soft 4-tick safety buffer | Without it the MIP trickled 62 L per tick just in time and never kept a buffer |
| 2026-09-29 | Resilience | `DEMO_MASK_ERRORS=true` (default): stage errors show as "fallback", raw exception text is replaced, predict falls back to known rates then the published profiles, a never-reached simulator shows the hard-coded baseline world (`pipeline/demo_data.py`, never posted from), the dashboard payload falls back to the last good one; every mask logs `ERROR MASKED ...` with the traceback | User requirement: no error may reach the frontend during the demo; the log keeps the evidence |
| 2026-09-29 | Intelligence | Demand noise is uniform ±profile noise (measured: ratios 0.900-1.100), so the error floor is noise/√3; past demand is de-spiked by event windows, including RESOLVED spikes | Measured on simulator/dataset; the old floor overstated risk 1.7×, and resolved spikes leaked into the base rate after a restart |
| 2026-09-29 | Decisions | Unanswered approval cards auto-approve at a **dynamic deadline**: each tick the simulator copy prices waiting 0..H ticks; the card waits while the extra unserved liters stay within `demand per tick × (DEADLINE_TOLERANCE_TICKS + DEADLINE_CONFIDENCE_SCALE × (1 − confidence))`, capped by APPROVAL_TTL_TICKS; at the deadline it is re-checked and resized (fair share, bridge amount for low confidence, dispatch/tank room) or expired if no longer needed; logged as `auto-deadline` | User decision: human review must never starve a station; unsure forecasts buy the operator more time |
| 2026-09-29 | Integration | Simulator timeout 10 s, timeouts are not retried (connection errors / 5xx still are); SSE idle timeout `SIMULATOR_STREAM_IDLE_SECONDS` (30 s) reconnects a silent stream | Tested with injected faults: a 5 s latency fault made every 5 s-timeout read fail (x3 with retries), so the pipeline did nothing; a half-open stream was never noticed |
| 2026-09-29 | Monitoring | `prometheus-client` with its own registry; metrics labeled by route template, not raw path; `/status` computes p95 / error rate from an in-process 5-min window so it works without Prometheus | Bounded label cardinality; the JSON status must not depend on the monitoring stack being up |
| 2026-09-29 | Monitoring | Prometheus + Grafana as compose services; datasource and dashboard provisioned from files, dashboard JSON generated by a script | One command brings up the System Status view; the dashboard is reviewable code |
| 2026-09-29 | Pipeline | CPU-bound stages (predict, MIP decide) run in `asyncio.to_thread` | Load test: running them on the event loop stalled every API request for ~0.5 s per tick; throughput fell as clients were added |
| 2026-09-29 | Monitoring | Load-test results go to their own Grafana dashboard via metrics the load tester serves while it runs (scraped by Prometheus), not a JSON/CSV datasource plugin | No extra Grafana plugin or Pushgateway; the live run and the per-step results share one data path |
| 2026-09-29 | Decisions | **Urgent risk alone no longer needs the operator** (supersedes "urgent" in the "Important" rows above): the operator is asked only when there is a trade-off (low confidence, over fair share, backup route, depot not OPEN, active crisis, stale data, auto-post off, or an urgent shipment taking more than `URGENT_REVIEW_DEPOT_SHARE` of the depot's stock). "Truck arrives after the tank is empty" is **not** a trigger | User decision: on the fastest open road there is nothing better to choose, so a review only added unserved demand at a station that is already dry; draining a depot is a real choice between stations |
| 2026-09-29 | Decisions | **Stockout risk sends shipments to the operator again** (supersedes "urgent risk alone no longer needs the operator"): half-empty tank emptying within the horizon, stockout probability ≥ 30%, < 4 ticks margin over the fastest truck, or unserved demand even with the shipment; each reason states its numbers; `REVIEW_RISK_ENABLED=false` restores the previous policy | User decision: review should start when a station is at real risk, not when it is almost dry; the dynamic approval deadline still auto-approves before waiting costs fuel |
| 2026-09-29 | Decisions | Dynamic deadline gets a **never-dry cap**: approve while the projected tank still covers (wait + transit + `DEADLINE_SAFETY_TICKS`) × demand per tick, whatever the loss tolerance allows | User requirement: human review must never let a station reach zero |
