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
| Database | Supabase Postgres (via `asyncpg`, session pooler) |
| Files    | Supabase Storage (REST API via `httpx`), as a repository with no routes |
| AI       | Gemini, Groq, OmniRoute behind one `LLMClient` with an env-configured fallback chain |
| Frontend | React 19 + Vite operator dashboard (`frontend/`), live via the backend's SSE |
| Simulator | BUP Fuel Supply Simulator on :8000 (separate compose in `simulator/`); backend on :8001 |
| Run      | Docker + Docker Compose (hot reload) |

## 2. Repository layout

```
.
├── backend/              FastAPI app (see §3)
├── frontend/             operator dashboard (React + Vite, see §8)
├── simulator/            simulator compose file + dataset collector
├── slide/                presentation material
├── docker-compose.yml    runs the backend
├── explainability.md     decisions behind the AI explanations (Ask AI)
├── design.md             this file
├── features.md           feature list the agent builds from
└── CLAUDE.md             entry point for Claude Code (points here)
```

The backend owns all simulator access; the browser only talks to the backend.
Routes: `GET /health`, the `/ai` endpoints, the pipeline/dashboard endpoints,
`/recommendations` (see §7a) and `/explain` (see §7b).

## 3. Backend

### 3.1 Folder by folder (`backend/app/`)

| Folder / file | What it holds | Rules |
|---|---|---|
| `main.py` | `create_app()`: middlewares, routers, lifespan (create tables, build the AI client, close HTTP clients). | Keep it thin. |
| `core/config.py` | `Settings` (pydantic-settings). **Every** env var is declared here. Also builds the Supabase DB URL. | Never read `os.environ` elsewhere; use `get_settings()`. |
| `core/database.py` | Async engine, `SessionLocal`, `get_db` dependency, `init_db()` (`create_all`). | |
| `core/exceptions.py` | `AppException` and its subclasses (`BadRequestError`, `UnauthorizedError`, `ForbiddenError`, `NotFoundError`, `ConflictError`, `ExternalServiceError`, `ServiceUnavailableError`). | Services raise these; never return error dicts by hand. |
| `core/dependencies.py` | Wiring: `get_<x>_service` builds a service with its repositories and clients. Annotated types `DbSession`, `LLM` (AI client), `Storage` (Supabase Storage). | One `get_<feature>_service` per feature. |
| `controllers/` | FastAPI routers (HTTP layer only). Now: `health_controller.py`, `ai_controller.py`, `pipeline_controller.py` (dashboard, SSE stream, manual run, snapshots), `recommendation_controller.py` (list, approve/edit, reject), `explain_controller.py` (catalog, context preview, free question, Ask AI per recommendation). `__init__.py` registers every router into `api_router`. | Parse input, call one service method, return. No business logic, no DB access. |
| `services/` | Business logic. Now: `ai_service.py`, `pipeline_service.py` (one pipeline pass per tick), `recommendation_service.py` (approval + posting), `dashboard_service.py` (cached state + SSE), `explain_service.py` (pipeline snapshot → metrics → LLM → stored Q&A). One `<name>_service.py` with a `<Name>Service` class per feature. | No FastAPI imports (except `UploadFile`); raise `AppException`s. |
| `repositories/` | Data access. Now: `storage_repository.py` (Supabase Storage), `simulator_repository.py` (simulator `/v1` client: timeout, retry + backoff, circuit breaker, stale-header detection, both error shapes), `snapshot_repository.py`, `recommendation_repository.py`, `action_question_repository.py`. One `<name>_repository.py` per table. | The only layer that touches the DB session, the storage API or the simulator. |
| `models/` | SQLAlchemy ORM: `base.py` has `Base` and `TimestampMixin` (`created_at`, `updated_at`); `snapshot.py`, `recommendation.py`, `action_question.py` (Q&A per recommendation). | Import every new model in `models/__init__.py`, or its table won't be created. |
| `schemas/` | Pydantic request/response models. Now: `common.py` (`ErrorResponse`, generic `Page[T]`), `ai.py`, `pipeline.py`, `recommendation.py`, `explain.py`. Per resource: `<Name>Create`, `<Name>Update`, `<Name>Read`. | Always set a `response_model`; never return ORM objects raw. |
| `middlewares/` | `cors.py`, `request_logging.py`, `error_handler.py`, `rate_limiter.py`, and `setup_middlewares()` in `__init__.py`. | See §3.3. |
| `utils/` | `logger.py` (logging with request ids), `pagination.py` (`page_params` dependency + `build_page` → `Page[T]`). | Framework-agnostic helpers. |
| `ai/` | Provider-agnostic LLM module (see §4). | |
| `explainability/` | LLM explanations (see §7b): `types.py` (`Subject`, `Snapshot`, `MetricContext`), `metrics.py` (`@metric` registry + built-in metrics over the pipeline's World/Forecast/Alert), `profiles.json` (**which metrics each question type sends to the LLM, params, suggested questions**), `context.py` (load profiles, build the JSON context), `prompt.py` (system prompt + messages). | Metrics are pure (no I/O) and never recompute detect/predict; `ExplainService` does the I/O. |
| `pipeline/` | Tick pipeline stages (see §7a): `types.py` (World, Forecast, Plan, Alert), `validate.py`, `detect.py`, `predict.py`, `decide.py`, `explain.py`, `state.py` (in-memory cache + SSE broadcaster), `watcher.py` (SSE listener + polling fallback), `__init__.py` (stage builders: **swap in a model here**). | Stages are pure (no I/O); `PipelineService` does the I/O. |

`backend/tests/`: pytest suite with fake AI providers, a mocked Supabase Storage API, and
a throwaway SQLite database. Run it with `cd backend && .venv/bin/pytest`.

### 3.2 Request flow

```
HTTP → CORS → RequestLogging → CatchAllError → RateLimit → controller
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

### 3.4 Database (Supabase)

- The DB URL is built from `SUPABASE_URL` (project ref) + `SUPABASE_PASSWORD`.
- `SUPABASE_POOLER_HOST` set → connects to the **session pooler** as `postgres.<ref>` (IPv4). Empty → direct `db.<ref>.supabase.co` (IPv6-only: won't work from Docker or most home networks).
- `DATABASE_URL` set → overrides everything (tests use SQLite; handy for offline work).
- Tables are created on startup with `Base.metadata.create_all`. There are no migrations, so changing an existing column means altering it by hand in the Supabase SQL editor (or dropping the table in dev).
- Small connection pool (5 + 5 overflow), because the pooler caps connections per project.
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
docker compose up --build        # backend :8000 (docs at /docs)

# or locally
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload
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
  - *important?* urgent risk, backup route, depot not OPEN, an ACTIVE crisis touching the station/region/depot/route,
    or `AUTO_POST_ENABLED=false` → `PENDING_APPROVAL`; otherwise `APPROVED` (auto).
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
| 2026-09-29 | DevOps | Docker Compose with source mounts + hot reload; no local DB container | One command to run everything; DB is hosted |
| 2026-09-29 | Scope | **No frontend**: the project is backend-only | User decision for the BUP Fuel Supply Simulator challenge |
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
