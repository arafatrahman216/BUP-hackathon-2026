# Design

This is the single source of truth for how this project is built. It covers what lives
in each folder, the conventions to follow, and a log of design decisions.
**Coding agents: read this before writing code, and add to the decision log whenever you
make a new design choice (frontend or backend).**

Feature requirements live in [features.md](features.md).

---

## 1. Stack

| Layer    | Choice |
|----------|--------|
| Backend  | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) |
| Database | Supabase Postgres (via `asyncpg`, session pooler) |
| Files    | Supabase Storage (REST API via `httpx`) |
| AI       | Gemini, Groq, OmniRoute behind one `LLMClient` with an env-configured fallback chain |
| Frontend | Vite + React 19 (JavaScript), react-router 7, CSS Modules, Vitest |
| Run      | Docker + Docker Compose (hot reload for both apps) |

## 2. Repository layout

```
.
├── backend/              FastAPI app (see §3)
├── frontend/             Vite React app (see §5)
├── slide/                presentation material
├── docker-compose.yml    runs backend + frontend
├── design.md             this file
├── features.md           feature list the agent builds from
└── CLAUDE.md             entry point for Claude Code (points here)
```

## 3. Backend

### 3.1 Folder by folder (`backend/app/`)

| Folder / file | What it holds | Rules |
|---|---|---|
| `main.py` | `create_app()`: middlewares, routers, lifespan (create tables, build the AI client, close HTTP clients). | Keep it thin. |
| `core/config.py` | `Settings` (pydantic-settings). **Every** env var is declared here. Also builds the Supabase DB URL. | Never read `os.environ` elsewhere; use `get_settings()`. |
| `core/database.py` | Async engine, `SessionLocal`, `get_db` dependency, `init_db()` (`create_all`). | |
| `core/exceptions.py` | `AppException` and its subclasses (`NotFoundError`, `ConflictError`, `BadRequestError`, `UnauthorizedError`, `ForbiddenError`, `ExternalServiceError`, `ServiceUnavailableError`). | Services raise these; never return error dicts by hand. |
| `core/dependencies.py` | Wiring: `get_<x>_service` builds a service with its repositories and clients. `DbSession`, `LLM` and `Storage` annotated types. | One `get_<feature>_service` per feature. |
| `controllers/` | FastAPI routers (HTTP layer only): parse input, call one service method, return. One file per resource: `<name>_controller.py`. `__init__.py` registers all routers into `api_router`. | No business logic, no DB access. |
| `services/` | Business logic: validation rules, orchestration, AI calls. `<name>_service.py` with a `<Name>Service` class. | No FastAPI imports (except `UploadFile`); raise `AppException`s. |
| `repositories/` | Data access. `BaseRepository[Model]` gives generic async CRUD (`get`, `list`, `count`, `create`, `update`, `delete`). `storage_repository.py` wraps Supabase Storage. | Only layer that touches the DB session or storage API. |
| `models/` | SQLAlchemy ORM models (`Base`, `TimestampMixin`). | Import every new model in `models/__init__.py`, or its table won't be created. |
| `schemas/` | Pydantic request/response models. Per resource: `<Name>Create`, `<Name>Update`, `<Name>Read`. `common.py` has `ErrorResponse` and `Page[T]`. | Never return ORM objects without a `response_model`. |
| `middlewares/` | `cors.py`, `request_logging.py`, `error_handler.py`, `rate_limiter.py`, and `setup_middlewares()` in `__init__.py`. | See §3.3. |
| `utils/` | Framework-agnostic helpers: `logger.py` (logging with request ids), `pagination.py` (`page_params` dependency, `build_page`). | |
| `ai/` | Provider-agnostic LLM module (see §4). | |

`backend/tests/`: pytest suite with fake AI providers, a mocked Supabase Storage API, and
a throwaway SQLite database. Run it with `cd backend && pytest`.

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
   "error": {"code": "NOT_FOUND", "message": "Item 3 not found", "details": null, "request_id": "a1b2c3"}}
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
- **Rate limiter**: in-memory sliding window per client IP, applied only to paths starting with `RATE_LIMIT_PATH_PREFIXES` (default `/api/v1/ai`) and only to non-GET requests, so metadata reads like `GET /ai/providers` don't use up the quota. A route outside `/ai` that calls the LLM (e.g. `POST /items/{id}/generate-description`) is **not** limited unless you add its prefix.

Successful responses are the plain resource (no envelope). Lists use `Page[T]`:
`{items, total, page, page_size, pages}`.

### 3.4 Database (Supabase)

- The DB URL is built from `SUPABASE_URL` (project ref) + `SUPABASE_PASSWORD`.
- `SUPABASE_POOLER_HOST` set → connects to the **session pooler** as `postgres.<ref>` (IPv4). Empty → direct `db.<ref>.supabase.co` (IPv6-only: won't work from Docker or most home networks).
- `DATABASE_URL` set → overrides everything (tests use SQLite; handy for offline work).
- Tables are created on startup with `Base.metadata.create_all`. There are no migrations, so changing an existing column means altering it by hand in the Supabase SQL editor (or dropping the table in dev).
- Small connection pool (5 + 5 overflow), because the pooler caps connections per project.
- Each repository write commits by default. Pass `commit=False` to group several writes, then call `await session.commit()` yourself.

### 3.5 File storage (Supabase Storage)

`StorageRepository` talks to `SUPABASE_URL/storage/v1` with the service-role key.
`FileService` sanitizes names (`<folder>/<8-char-uuid>-<safe-name>`), rejects `..`, and
enforces `MAX_UPLOAD_MB`. Endpoints: `GET /files?prefix=`, `POST /files` (multipart
`file`, `folder`), `GET /files/signed-url?path=&expires_in=`, `DELETE /files?path=`.
The bucket is public, so `public_url` works. For a private bucket, use `signed_url`.
**The service-role key bypasses Row Level Security and must never reach the frontend.**

### 3.6 Adding a backend feature (copy Items)

1. `models/<name>.py`, then import it in `models/__init__.py`
2. `schemas/<name>.py` with `Create` / `Update` / `Read`
3. `repositories/<name>_repository.py`: `class XRepository(BaseRepository[X]): model = X`
4. `services/<name>_service.py`: business rules, raising `AppException`s
5. `core/dependencies.py`: `get_<name>_service`
6. `controllers/<name>_controller.py`, then register it in `controllers/__init__.py`
7. `tests/test_<name>.py`

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

**Fallback configuration (env):**
- `AI_PROVIDER_ORDER=gemini,groq,omniroute`: tried left to right. Entries can repeat (`gemini,gemini,groq` retries Gemini once) and can pin a model (`groq:llama-3.1-8b-instant`).
- `AI_FALLBACK_ENABLED=false` → only the first entry is used.
- Providers without credentials are **skipped** (recorded as `skipped` in `attempts`).
- An unknown provider name in the chain fails at startup.
- Passing `provider=` (and optionally `model=`) to `chat()` bypasses the chain.

**Using AI in a feature:** inject `LLM` into your service (see `ItemService.generate_description`), then:
```python
reply = await self.llm.complete("Summarize: ...", system="You are ...")   # reply.text
data  = await self.llm.complete_json('Return {"tags": [string]} for: ...')  # parsed JSON
```

**Adding a provider:**
- OpenAI-compatible (OpenAI, OpenRouter, Together, Mistral, Ollama…): subclass `OpenAICompatibleProvider` with `name` and `from_settings`, decorate it with `@register_provider`, add `<NAME>_API_KEY/_MODEL/_BASE_URL` to `Settings` and `.env.example`, and import the module in `providers/__init__.py`.
- Other APIs: subclass `BaseLLMProvider` and implement `generate()` (see `gemini.py`).

Not implemented yet: streaming responses, tool/function calling.

## 5. Frontend (`frontend/`)

Vite + React 19 (JavaScript), react-router 7, CSS Modules, `lucide-react` icons, Vitest + Testing Library.

### 5.1 Folder by folder (`frontend/src/`)

| Folder / file | What it holds | Rules |
|---|---|---|
| `api/api.js` | **The only module that talks HTTP.** Base URL from `VITE_API_BASE_URL`; `request()` wraps fetch (JSON or FormData bodies, query params, timeouts, Bearer token); every failure becomes an `ApiError` (`status, code, message, details, requestId, retryAfter`, plus `fieldErrors` for forms); on a 401 it clears the token and fires `auth:unauthorized`. Endpoints are grouped as `healthApi`, `itemsApi`, `aiApi`, `filesApi`. | Components never call `fetch` directly. Add endpoint functions here. |
| `hooks/` | `useAsync` (load data: `data/error/loading/refetch`, cancels stale requests), `useMutation` (writes: returns `{data, error}`, optional toasts), `useItems` / `useFiles` (resource hooks, the pattern to copy), `useDebounce`, `useToast`, `useAuth`, `useTheme`, `useCopyToClipboard`. Re-exported from `hooks/index.js`. | Pages get data through hooks, not by calling `api.js` inline. |
| `context/` | `AuthProvider` (token state synced with `api.js`), `ToastProvider`, and `AppProviders`, which wraps both. | |
| `components/ui/` | Reusable primitives, each with its own `.module.css`: Button, Input, Textarea, Select, Switch, Field, Card, Badge, Modal, ConfirmDialog, Spinner, Skeleton, EmptyState, ErrorState, Pagination, Toast, Table. Exported from `components/ui/index.js`. | No data fetching in here. Reuse these before writing new markup. |
| `components/layout/` | AppLayout (sidebar + header; the sidebar becomes a drawer below 960px), Sidebar, Header, PageHeader, and `navigation.js` (the nav items). | Add new pages to `navigation.js`. |
| `pages/<Name>/` | One folder per page: `<Name>Page.jsx` plus its page-only components. Current pages: Dashboard, Items (the CRUD example), AIPlayground, Files (Supabase Storage), NotFound. | Pages are lazy-loaded in `App.jsx`. |
| `styles/global.css` | Design tokens as CSS variables (neutral palette, indigo accent, spacing, radius, shadows, Inter / JetBrains Mono), light and dark themes (dark follows the OS, with a header toggle to override), and the reset. | Use the tokens. Don't hard-code colors. |
| `utils/` | `cn` (classnames), `format` (dates, bytes, money), `errors` helpers. | |
| `test/` | Vitest setup and render helpers. Tests sit next to their code (`*.test.js(x)`). | |

### 5.2 Adding a frontend feature

1. Add endpoint functions to `api/api.js` (e.g. `ordersApi`).
2. Add a hook in `hooks/` (copy `useItems`).
3. Create `pages/Orders/OrdersPage.jsx` (+ `.module.css`) and build it from `components/ui`.
4. Add the route in `App.jsx` and the nav entry in `components/layout/navigation.js`.
5. Show errors with `ErrorState`, a toast, or `error.fieldErrors` on forms. The backend error shape is already parsed.

**Auth:** the backend has no auth yet. The plumbing is ready: `setToken()` / `useAuth()` store a token, `api.js` sends it as `Authorization: Bearer`, and a 401 logs the user out. To add real auth, add a login endpoint and page and verify the token in a backend dependency.

## 6. Configuration

- Backend: `backend/.env` (gitignored). The documented template is `backend/.env.example`, and every key is declared in `core/config.py`. Empty values fall back to the defaults.
- Frontend: `frontend/.env` → `VITE_API_BASE_URL` (the backend base URL, including `/api/v1`).
- Docker Compose reads both `.env` files. Ports can be overridden with `BACKEND_PORT` / `FRONTEND_PORT`.

## 7. Running

```bash
docker compose up --build        # frontend :5173, backend :8000 (docs at /docs)

# or locally
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload
.venv/bin/pytest
cd frontend && npm install && npm run dev
```

## 8. Decision log

Add a row whenever a design choice is made. Newest at the bottom.

| Date | Area | Decision | Why |
|---|---|---|---|
| 2026-09-29 | Backend | Layered structure: controllers → services → repositories → models; schemas for I/O | Clear place for everything; easy to copy the Items resource |
| 2026-09-29 | Backend | Async SQLAlchemy 2.0 + `create_all` on startup, no Alembic | Hackathon speed; add migrations if the schema stabilizes |
| 2026-09-29 | Backend | Repository writes commit by default (`commit=False` to batch) | Commit happens before the response is sent; simple mental model |
| 2026-09-29 | Backend | One JSON error shape for every error; successful responses are unwrapped | Frontend handles errors in one place; OpenAPI stays accurate |
| 2026-09-29 | Backend | In-memory rate limiter on AI route prefixes | Protects free-tier AI quotas; swap for Redis if running multiple instances |
| 2026-09-29 | AI | Direct REST calls via `httpx` instead of vendor SDKs | Fewer dependencies, one error-handling path, easy to add providers |
| 2026-09-29 | AI | Provider chain + fallback flag in env; repeats = retries; `provider:model` pins | User requirement: configurable fallback and order |
| 2026-09-29 | Database | **Supabase** Postgres, URL built from `SUPABASE_*` vars; session pooler because the direct host is IPv6-only | User requirement; must work from Docker |
| 2026-09-29 | Storage | Supabase Storage through `StorageRepository` (REST), service-role key server-side only | Uses the provided bucket; keeps secrets off the client |
| 2026-09-29 | Frontend | Plain CSS Modules + CSS-variable design tokens, no UI kit | Full control over a clean look, zero lock-in, light/dark from one token set |
| 2026-09-29 | Frontend | All HTTP through `api/api.js`; one `ApiError` type; data through hooks | One place for base URL, auth and error parsing; pages stay simple |
| 2026-09-29 | Frontend | Backend URL in `frontend/.env` (`VITE_API_BASE_URL`) | Switch backends without code changes |
| 2026-09-29 | Backend | Rate limiter counts only non-GET requests on AI prefixes | Dashboard loads of `GET /ai/providers` shouldn't use up the AI quota |
| 2026-09-29 | DevOps | Docker Compose with source mounts + hot reload; no local DB container | One command to run everything; DB is hosted |
