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
    # Optional full override (tests use SQLite). Empty -> built from the SUPABASE_* values.
    DATABASE_URL: str = ""
    DB_ECHO: bool = False

    # --- Rate limiting (in-memory, per client IP) ---
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 20
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_PATH_PREFIXES: str = "/api/v1/ai"

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
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"

    OMNIROUTE_API_KEY: str = ""  # optional if your OmniRoute instance doesn't require one
    OMNIROUTE_MODEL: str = ""
    OMNIROUTE_BASE_URL: str = "http://localhost:20128/v1"

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
