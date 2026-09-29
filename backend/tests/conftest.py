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
    "PIPELINE_ENABLED": "false",
    "PREDICTOR": "moving_average",  # the API tests pin the baseline; tests/test_intelligence.py covers the rest
    "PLANNER": "rules",
    "DEMO_MASK_ERRORS": "false",  # tests assert raw stage errors; test_masking.py turns it on
    "SIMULATOR_RETRIES": "0",
    "SIMULATOR_BACKOFF_SECONDS": "0",
    "SIMULATOR_BREAKER_THRESHOLD": "100",
})

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.ai import ChatMessage, LLMClient, LLMResponse, ProviderError, get_llm_client  # noqa: E402
from app.ai.client import ChainEntry  # noqa: E402
from app.ai.providers.base import BaseLLMProvider  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.pipeline.state import reset_pipeline_state  # noqa: E402
from app.repositories.simulator_repository import get_simulator_repository  # noqa: E402
from tests.fake_simulator import FakeSimulator  # noqa: E402


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
def fake_sim() -> FakeSimulator:
    return FakeSimulator()


@pytest.fixture
async def app(fake_llm, fake_sim):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()  # fresh app -> fresh rate-limiter state
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    sim_repo = fake_sim.repository()
    app.dependency_overrides[get_simulator_repository] = lambda: sim_repo
    reset_pipeline_state()  # fresh cache + lock bound to this test's event loop
    return app


@pytest.fixture
def manual_approval(monkeypatch):
    """Every plan becomes an operator card (urgency alone is auto-posted)."""
    monkeypatch.setattr(get_settings(), "AUTO_POST_ENABLED", False)


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
