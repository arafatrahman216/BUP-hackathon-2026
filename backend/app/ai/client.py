"""LLMClient: the single entry point the rest of the app uses for AI.

It walks the provider chain from AI_PROVIDER_ORDER, skipping providers that aren't
configured and falling back to the next entry on failure (if AI_FALLBACK_ENABLED).
"""

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from app.ai.exceptions import AIResponseParseError, AllProvidersFailedError, UnknownProviderError
from app.ai.providers.base import BaseLLMProvider
from app.ai.registry import get_provider_classes
from app.ai.types import ChatMessage, LLMResponse, ProviderAttempt
from app.core.config import Settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True)
class ChainEntry:
    provider: str
    model: str | None = None  # None -> the provider's default model

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}" if self.model else self.provider


def parse_provider_order(entries: list[str]) -> list[ChainEntry]:
    """["gemini", "groq:llama-3.1-8b-instant"] -> [ChainEntry("gemini"), ChainEntry("groq", "llama-3.1-8b-instant")]"""
    chain = []
    for entry in entries:
        provider, _, model = entry.partition(":")
        chain.append(ChainEntry(provider.strip().lower(), model.strip() or None))
    return chain


class LLMClient:
    def __init__(
        self,
        providers: dict[str, BaseLLMProvider],
        chain: list[ChainEntry],
        *,
        fallback_enabled: bool = True,
        default_temperature: float | None = None,
        default_max_tokens: int | None = None,
    ) -> None:
        for entry in chain:
            if entry.provider not in providers:
                raise UnknownProviderError(entry.provider, list(providers))
        if not chain:
            raise ValueError("AI provider chain is empty; set AI_PROVIDER_ORDER")
        self.providers = providers
        self.chain = chain
        self.fallback_enabled = fallback_enabled
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens

    @classmethod
    def from_settings(cls, settings: Settings) -> "LLMClient":
        providers = {name: p.from_settings(settings) for name, p in get_provider_classes().items()}
        return cls(
            providers,
            parse_provider_order(settings.ai_provider_order),
            fallback_enabled=settings.AI_FALLBACK_ENABLED,
            default_temperature=settings.AI_DEFAULT_TEMPERATURE,
            default_max_tokens=settings.AI_DEFAULT_MAX_TOKENS,
        )

    @property
    def active_chain(self) -> list[ChainEntry]:
        return self.chain if self.fallback_enabled else self.chain[:1]

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        provider: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Run a conversation through the chain. Passing `provider` bypasses the
        chain and calls only that provider (optionally with `model`)."""
        if provider:
            provider = provider.lower()
            if provider not in self.providers:
                raise UnknownProviderError(provider, list(self.providers))
            chain = [ChainEntry(provider, model)]
        else:
            chain = self.active_chain

        temperature = self.default_temperature if temperature is None else temperature
        max_tokens = self.default_max_tokens if max_tokens is None else max_tokens

        attempts: list[ProviderAttempt] = []
        for entry in chain:
            llm = self.providers[entry.provider]
            model_name = entry.model or llm.model or None
            if not llm.is_configured:
                attempts.append(ProviderAttempt(
                    provider=entry.provider, model=model_name, status="skipped", error="not configured"
                ))
                continue

            started = time.perf_counter()
            try:
                response = await llm.generate(
                    messages,
                    model=entry.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    json_mode=json_mode,
                )
            except Exception as exc:  # any provider failure -> try the next entry
                latency = (time.perf_counter() - started) * 1000
                logger.warning("AI provider %s failed after %.0fms: %s", entry, latency, exc)
                attempts.append(ProviderAttempt(
                    provider=entry.provider, model=model_name, status="failed",
                    error=str(exc)[:500], latency_ms=round(latency, 1),
                ))
                continue

            latency = (time.perf_counter() - started) * 1000
            attempts.append(ProviderAttempt(
                provider=entry.provider, model=response.model, status="success", latency_ms=round(latency, 1)
            ))
            response.attempts = attempts
            return response

        raise AllProvidersFailedError(attempts)

    async def complete(self, prompt: str, *, system: str | None = None, **kwargs: Any) -> LLMResponse:
        """Single-turn helper: `await llm.complete("Summarize ...", system="You are ...")`."""
        messages = [ChatMessage(role="system", content=system)] if system else []
        messages.append(ChatMessage(role="user", content=prompt))
        return await self.chat(messages, **kwargs)

    async def complete_json(self, prompt: str, *, system: str | None = None, **kwargs: Any) -> Any:
        """Like complete(), but asks for JSON and returns the parsed value.
        Mention the expected JSON shape in the prompt."""
        response = await self.complete(prompt, system=system, json_mode=True, **kwargs)
        try:
            return json.loads(_CODE_FENCE.sub("", response.text.strip()))
        except json.JSONDecodeError as exc:
            raise AIResponseParseError(f"{response.provider} returned invalid JSON: {response.text[:200]}") from exc

    def describe(self) -> dict[str, Any]:
        return {
            "fallback_enabled": self.fallback_enabled,
            "provider_order": [str(e) for e in self.chain],
            "active_chain": [str(e) for e in self.active_chain],
            "providers": [
                {"name": name, "configured": p.is_configured, "default_model": p.model or None}
                for name, p in self.providers.items()
            ],
        }

    async def aclose(self) -> None:
        for llm in self.providers.values():
            await llm.aclose()
