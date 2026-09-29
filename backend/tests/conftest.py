import os
import tempfile

# Must be set before the app (and its settings) are imported.
_db_file = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.update({
    "APP_ENV": "test",
    "DEBUG": "false",
    "CORS_ORIGINS": "http://localhost:3000",
    "DATABASE_URL": f"sqlite+aiosqlite:///{_db_file}",
    "RATE_LIMIT_ENABLED": "true",
    "RATE_LIMIT_REQUESTS": "3",
    "RATE_LIMIT_WINDOW_SECONDS": "60",
    "AI_PROVIDER_ORDER": "gemini,groq",
    "AI_FALLBACK_ENABLED": "true",
})

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.ai import ChatMessage, LLMClient, LLMResponse, ProviderError, get_llm_client  # noqa: E402
from app.ai.client import ChainEntry  # noqa: E402
from app.ai.providers.base import BaseLLMProvider  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402


class FakeProvider(BaseLLMProvider):
    """Test double: succeeds with `reply`, or fails `fail_times` times first."""

    def __init__(self, name: str, *, reply: str = "ok", fail_times: int = 0, configured: bool = True) -> None:
        super().__init__(api_key="key" if configured else "", model=f"{name}-model", base_url="http://fake")
        self.name = name
        self.reply = reply
        self.fail_times = fail_times
        self.calls = 0

    @classmethod
    def from_settings(cls, settings):
        raise NotImplementedError

    async def generate(self, messages: list[ChatMessage], *, model=None, **kwargs) -> LLMResponse:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ProviderError(self.name, "boom")
        return LLMResponse(text=self.reply, provider=self.name, model=model or self.model)


def make_client(order: str, providers: list[FakeProvider], fallback: bool = True) -> LLMClient:
    chain = [ChainEntry(*(e.split(":", 1) + [None])[:2]) for e in order.split(",")]
    return LLMClient({p.name: p for p in providers}, chain, fallback_enabled=fallback)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def fake_llm() -> LLMClient:
    return make_client("gemini,groq", [
        FakeProvider("gemini", fail_times=100),
        FakeProvider("groq", reply="A shiny description."),
    ])


@pytest.fixture
async def app(fake_llm):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()  # fresh app -> fresh rate-limiter state
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    return app


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
