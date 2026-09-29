"""AI module: provider-agnostic LLM access with an env-configured fallback chain.

Usage in a service:
    from app.ai import LLMClient
    reply = await llm.complete("Write a haiku about FastAPI")
    data = await llm.complete_json('Return {"tags": [...]} for: ...')

Get the client via the `get_llm_client` FastAPI dependency (see core/dependencies.py).
"""

from app.ai.client import ChainEntry, LLMClient
from app.ai.exceptions import (
    AIError,
    AIResponseParseError,
    AllProvidersFailedError,
    ProviderError,
    UnknownProviderError,
)
from app.ai.types import ChatMessage, LLMResponse, ProviderAttempt, TokenUsage
from app.core.config import get_settings

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient.from_settings(get_settings())
    return _client


async def close_llm_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


__all__ = [
    "AIError",
    "AIResponseParseError",
    "AllProvidersFailedError",
    "ChainEntry",
    "ChatMessage",
    "LLMClient",
    "LLMResponse",
    "ProviderAttempt",
    "ProviderError",
    "TokenUsage",
    "UnknownProviderError",
    "close_llm_client",
    "get_llm_client",
]
