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
| Run      | Docker + Docker Compose (hot reload) |

## 2. Repository layout

```
.
├── backend/              FastAPI app (see §3)
├── slide/                presentation material
├── docker-compose.yml    runs the backend
├── design.md             this file
├── features.md           feature list the agent builds from
└── CLAUDE.md             entry point for Claude Code (points here)
```

The project is **backend-only** (no frontend). The template ships no demo business
resources: the only routes are `GET /health` and the `/ai` endpoints. Everything else gets
built from features.md.

## 3. Backend

### 3.1 Folder by folder (`backend/app/`)

| Folder / file | What it holds | Rules |
|---|---|---|
| `main.py` | `create_app()`: middlewares, routers, lifespan (create tables, build the AI client, close HTTP clients). | Keep it thin. |
| `core/config.py` | `Settings` (pydantic-settings). **Every** env var is declared here. Also builds the Supabase DB URL. | Never read `os.environ` elsewhere; use `get_settings()`. |
| `core/database.py` | Async engine, `SessionLocal`, `get_db` dependency, `init_db()` (`create_all`). | |
| `core/exceptions.py` | `AppException` and its subclasses (`BadRequestError`, `UnauthorizedError`, `ForbiddenError`, `NotFoundError`, `ConflictError`, `ExternalServiceError`, `ServiceUnavailableError`). | Services raise these; never return error dicts by hand. |
| `core/dependencies.py` | Wiring: `get_<x>_service` builds a service with its repositories and clients. Annotated types `DbSession`, `LLM` (AI client), `Storage` (Supabase Storage). | One `get_<feature>_service` per feature. |
| `controllers/` | FastAPI routers (HTTP layer only). Now: `health_controller.py`, `ai_controller.py`. `__init__.py` registers every router into `api_router`. | Parse input, call one service method, return. No business logic, no DB access. |
| `services/` | Business logic. Now: `ai_service.py`. One `<name>_service.py` with a `<Name>Service` class per feature. | No FastAPI imports (except `UploadFile`); raise `AppException`s. |
| `repositories/` | Data access. Now: `storage_repository.py` (Supabase Storage: `upload`, `list`, `create_signed_url`, `public_url`, `delete`). One `<name>_repository.py` per table. | The only layer that touches the DB session or the storage API. |
| `models/` | SQLAlchemy ORM: `base.py` has `Base` and `TimestampMixin` (`created_at`, `updated_at`). | Import every new model in `models/__init__.py`, or its table won't be created. |
| `schemas/` | Pydantic request/response models. Now: `common.py` (`ErrorResponse`, generic `Page[T]`) and `ai.py`. Per resource: `<Name>Create`, `<Name>Update`, `<Name>Read`. | Always set a `response_model`; never return ORM objects raw. |
| `middlewares/` | `cors.py`, `request_logging.py`, `error_handler.py`, `rate_limiter.py`, and `setup_middlewares()` in `__init__.py`. | See §3.3. |
| `utils/` | `logger.py` (logging with request ids), `pagination.py` (`page_params` dependency + `build_page` → `Page[T]`). | Framework-agnostic helpers. |
| `ai/` | Provider-agnostic LLM module (see §4). | |

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
