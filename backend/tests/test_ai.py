import pytest

from app.ai import AllProvidersFailedError, ChatMessage, UnknownProviderError, get_llm_client
from app.ai.client import parse_provider_order
from tests.conftest import FakeProvider, make_client

pytestmark = pytest.mark.anyio

MESSAGES = [ChatMessage(role="user", content="hi")]


def test_parse_provider_order():
    chain = parse_provider_order(["Gemini", "groq:llama-3.1-8b-instant", "ollama:llama3:8b"])
    assert [(e.provider, e.model) for e in chain] == [
        ("gemini", None), ("groq", "llama-3.1-8b-instant"), ("ollama", "llama3:8b"),
    ]


async def test_falls_back_in_order():
    gemini, groq = FakeProvider("gemini", fail_times=1), FakeProvider("groq", reply="from groq")
    response = await make_client("gemini,groq", [gemini, groq]).chat(MESSAGES)
    assert response.provider == "groq" and response.text == "from groq"
    assert [a.status for a in response.attempts] == ["failed", "success"]


async def test_repeated_entry_acts_as_retry():
    gemini, groq = FakeProvider("gemini", fail_times=1), FakeProvider("groq")
    response = await make_client("gemini,gemini,groq", [gemini, groq]).chat(MESSAGES)
    assert response.provider == "gemini" and gemini.calls == 2 and groq.calls == 0


async def test_fallback_disabled_uses_only_first():
    gemini, groq = FakeProvider("gemini", fail_times=1), FakeProvider("groq")
    with pytest.raises(AllProvidersFailedError) as exc:
        await make_client("gemini,groq", [gemini, groq], fallback=False).chat(MESSAGES)
    assert len(exc.value.attempts) == 1 and groq.calls == 0


async def test_unconfigured_provider_is_skipped():
    gemini, groq = FakeProvider("gemini", configured=False), FakeProvider("groq")
    response = await make_client("gemini,groq", [gemini, groq]).chat(MESSAGES)
    assert [a.status for a in response.attempts] == ["skipped", "success"]


async def test_model_pinned_in_chain():
    response = await make_client("groq:tiny", [FakeProvider("groq")]).chat(MESSAGES)
    assert response.model == "tiny"


async def test_explicit_provider_bypasses_chain():
    gemini, groq = FakeProvider("gemini"), FakeProvider("groq")
    response = await make_client("gemini,groq", [gemini, groq]).chat(MESSAGES, provider="groq", model="big")
    assert response.provider == "groq" and response.model == "big" and gemini.calls == 0


def test_unknown_provider_in_chain_fails_fast():
    with pytest.raises(UnknownProviderError):
        make_client("gemini,nope", [FakeProvider("gemini")])


async def test_complete_json_strips_code_fences():
    llm = make_client("groq", [FakeProvider("groq", reply='```json\n{"a": 1}\n```')])
    assert await llm.complete_json("give json") == {"a": 1}


def test_real_providers_are_registered():
    from app.ai.registry import get_provider_classes

    assert {"gemini", "groq", "omniroute"} <= set(get_provider_classes())


# --- HTTP API ---

async def test_chat_endpoint(client):
    response = await client.post("/api/v1/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    body = response.json()
    assert response.status_code == 200
    assert body["provider"] == "groq" and "raw" not in body
    assert response.headers["X-RateLimit-Limit"] == "3"


async def test_all_providers_failed_returns_502(client, fake_llm):
    fake_llm.providers["groq"].fail_times = 100
    response = await client.post("/api/v1/ai/generate", json={"prompt": "hi"})
    body = response.json()
    assert response.status_code == 502 and body["error"]["code"] == "AI_PROVIDERS_FAILED"
    assert [a["provider"] for a in body["error"]["details"]] == ["gemini", "groq"]


async def test_model_without_provider_is_rejected(client):
    response = await client.post("/api/v1/ai/generate", json={"prompt": "hi", "model": "x"})
    assert response.status_code == 422


async def test_unknown_provider_returns_400(client):
    response = await client.post("/api/v1/ai/generate", json={"prompt": "hi", "provider": "nope"})
    assert response.json()["error"]["code"] == "AI_UNKNOWN_PROVIDER"


async def test_rate_limit_on_ai_routes(client):
    body = {"prompt": "hi"}
    for _ in range(3):
        assert (await client.post("/api/v1/ai/generate", json=body)).status_code == 200
    limited = await client.post("/api/v1/ai/generate", json=body)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in limited.headers
    # Metadata reads and other routes are unaffected.
    assert (await client.get("/api/v1/ai/providers")).status_code == 200
    assert (await client.get("/api/v1/health")).status_code == 200


async def test_real_client_builds_from_settings():
    llm = get_llm_client()
    assert [str(e) for e in llm.chain] == ["gemini", "groq"]
