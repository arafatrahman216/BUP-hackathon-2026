"""Application settings, loaded from environment variables and backend/.env.

Every setting lives here. Access it through `get_settings()` (cached) instead of
reading os.environ directly.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "Hackathon API"
    APP_ENV: Literal["development", "production", "test"] = "development"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    # --- CORS (comma-separated origins, or "*") ---
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # --- Supabase (database + storage) ---
    SUPABASE_URL: str = ""  # https://<project-ref>.supabase.co
    SUPABASE_PASSWORD: str = ""  # database password
    SUPABASE_SERVICE_ROLE_KEY: str = ""  # server-side only, never send to the frontend
    SUPABASE_BUCKET_NAME: str = ""
    # Session pooler host (IPv4), e.g. aws-0-ap-southeast-1.pooler.supabase.com.
    # The direct host db.<ref>.supabase.co is IPv6-only, which Docker can't reach by default.
    SUPABASE_POOLER_HOST: str = ""
    MAX_UPLOAD_MB: int = 10

    # --- Database ---
    # Full SQLAlchemy URL. Docker Compose sets it to the local `db` Postgres container.
    # Empty -> built from the SUPABASE_* values (legacy option). Tests use SQLite.
    DATABASE_URL: str = ""
    DB_ECHO: bool = False
    DB_COMMAND_TIMEOUT_SECONDS: float = 10.0  # Postgres query timeout

    # --- Rate limiting (in-memory, per client IP) ---
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 20
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_PATH_PREFIXES: str = "/api/v1/ai,/api/v1/explain"

    # --- AI ---
    # Comma-separated chain, tried left to right. Entries may repeat (acts as a retry)
    # and may pin a model with "provider:model", e.g. "gemini,gemini,groq:llama-3.1-8b-instant".
    AI_PROVIDER_ORDER: str = "gemini,groq,omniroute"
    # false -> only the first entry of AI_PROVIDER_ORDER is used.
    AI_FALLBACK_ENABLED: bool = True
    AI_TIMEOUT_SECONDS: float = 60.0
    AI_DEFAULT_TEMPERATURE: float = 0.7
    AI_DEFAULT_MAX_TOKENS: int | None = None  # None -> provider default

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    OMNIROUTE_API_KEY: str = ""  # optional if your OmniRoute instance doesn't require one
    OMNIROUTE_MODEL: str = ""
    OMNIROUTE_BASE_URL: str = "http://localhost:20128/v1"

    # --- Simulator client ---
    SIMULATOR_BASE_URL: str = "http://localhost:8000"
    SIMULATOR_TIMEOUT_SECONDS: float = 10.0  # above the simulator latency fault (5 s) so slow reads still succeed
    SIMULATOR_RETRIES: int = 2  # extra attempts on connection errors / 5xx (timeouts are not retried)
    SIMULATOR_BACKOFF_SECONDS: float = 0.2  # doubles each retry
    SIMULATOR_BREAKER_THRESHOLD: int = 5  # consecutive failures that open the circuit
    SIMULATOR_BREAKER_COOLDOWN_SECONDS: float = 5.0
    SIMULATOR_STREAM_IDLE_SECONDS: float = 30.0  # SSE silent this long -> reconnect (polling covers the gap)

    # --- Pipeline (tick loop) ---
    PIPELINE_ENABLED: bool = True  # false -> no background tick watcher (tests)
    PIPELINE_POLL_SECONDS: float = 1.0  # /v1/instance polling fallback when SSE is down
    PIPELINE_SSE_ENABLED: bool = True
    FORECAST_WINDOW_TICKS: int = 8  # moving-average window for the demand rate
    SAFETY_TICKS: int = 8  # reorder when cover < transit + SAFETY_TICKS  ("watch")
    URGENT_MARGIN_TICKS: int = 2  # cover < transit + URGENT_MARGIN_TICKS -> "urgent"
    MIN_SHIPMENT_LITERS: float = 500.0
    DEPOT_RESERVE_LITERS: float = 0.0  # never plan below this depot level
    AUTO_POST_ENABLED: bool = True  # false -> every recommendation needs the operator
    APPROVAL_TTL_TICKS: int = 48  # unanswered recommendations expire after this many ticks...
    APPROVAL_MIN_SECONDS: float = 60.0  # ...and at least this many wall-clock seconds
    SNAPSHOT_EVERY_TICKS: int = 1  # save a world snapshot every N processed ticks
    # X-Simulator-Stale: "cautious" -> plan urgent needs only, with smaller shipments; "stop" -> don't act
    STALE_DATA_MODE: Literal["cautious", "stop"] = "cautious"
    STALE_QUANTITY_FACTOR: float = 0.5  # cautious mode: shipments are scaled by this

    # --- Explainability (LLM answers grounded in simulator data) ---
    EXPLAIN_PROVIDER: str = ""  # "" -> the AI_PROVIDER_ORDER chain (Gemini first); "gemini" -> Gemini only
    EXPLAIN_MODEL: str = ""  # model override; needs EXPLAIN_PROVIDER
    EXPLAIN_TEMPERATURE: float = 0.2
    EXPLAIN_MAX_TOKENS: int | None = None
    EXPLAIN_PROFILES_PATH: str = ""  # "" -> app/explainability/profiles.json
    EXPLAIN_HISTORY_LIMIT: int = 500  # demand-history rows read per question (max 2000)
    EXPLAIN_TEMPLATE_DELAY_SECONDS: float = 2.5  # pause (±30%) before a fixed-template answer, like an LLM reply; 0 = none

    DEMO_MASK_ERRORS: bool = True  # never show errors on the dashboard: backup data + "ERROR MASKED" log line

    # --- Intelligence (intelligence-plan.md §0.1) ---
    PREDICTOR: str = "structural"  # structural | moving_average (baseline)
    PLANNER: str = "optimizer"  # optimizer (strategic LP + MIP-MPC) | rules (baseline, always the fallback)
    FORECAST_HORIZON_TICKS: int = 24  # simulator-copy and MIP horizon (6 h at 15-min ticks)
    HISTORY_FETCH_ROWS: int = 1200  # demand-history rows read per tick (API max 2000)
    PLANNER_TIME_LIMIT_SECONDS: float = 2.0
    RATIONING_TRIGGER_DAYS: float = 3.0  # ration a fuel when the network has less than this left
    MIN_CONFIDENCE_AUTO: float = 0.5
    URGENT_REVIEW_DEPOT_SHARE: float = 0.5  # urgent shipment taking more than this share of the depot's stock -> operator
    REVIEW_RISK_ENABLED: bool = True  # depot-short review: the shipment competes with other stations for scarce fuel
    REVIEW_DEPOT_COVER_TICKS: float = 24.0  # depot short: left after this tick's shipments covers < this many ticks
    DEADLINE_TOLERANCE_TICKS: float = 2.0  # unanswered card auto-approves once waiting 1 more tick loses > this x tick demand
    DEADLINE_SAFETY_TICKS: int = 1  # never-dry cap: approve while the tank still covers wait + transit + this many ticks
    DEADLINE_CONFIDENCE_SCALE: float = 3.0  # extra ticks of tolerance x (1 - forecast confidence)
    MIN_REVIEW_SECONDS: float = 30.0  # human reading time, kept only while waiting costs nothing
    APPROVAL_HOLD_SECONDS: float = 60.0  # an unanswered card never auto-approves or expires before this age, at any tick speed
    ANOMALY_Z: float = 3.0  # single-tick z-score threshold (needs 2 ticks in a row)
    ANOMALY_CUSUM_K: float = 0.05  # CUSUM slack on log(actual/forecast)
    ANOMALY_CUSUM_H: float = 0.5  # CUSUM alarm level
    ANOMALY_MIN_LITERS: float = 20.0  # ignore ticks with less demand (night noise)

    @property
    def supabase_project_ref(self) -> str:
        host = self.SUPABASE_URL.split("//", 1)[-1]
        return host.split(".", 1)[0]

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        if not (self.SUPABASE_URL and self.SUPABASE_PASSWORD):
            raise ValueError("Database not configured: set SUPABASE_URL and SUPABASE_PASSWORD in backend/.env")
        ref = self.supabase_project_ref
        if self.SUPABASE_POOLER_HOST:
            host, user = self.SUPABASE_POOLER_HOST, f"postgres.{ref}"
        else:
            host, user = f"db.{ref}.supabase.co", "postgres"
        url = URL.create(
            "postgresql+asyncpg",
            username=user,
            password=self.SUPABASE_PASSWORD,
            host=host,
            port=5432,
            database="postgres",
        )
        return url.render_as_string(hide_password=False)

    @property
    def cors_origins(self) -> list[str]:
        return _split_csv(self.CORS_ORIGINS)

    @property
    def rate_limit_path_prefixes(self) -> list[str]:
        return _split_csv(self.RATE_LIMIT_PATH_PREFIXES)

    @property
    def ai_provider_order(self) -> list[str]:
        return _split_csv(self.AI_PROVIDER_ORDER)


@lru_cache
def get_settings() -> Settings:
    return Settings()
