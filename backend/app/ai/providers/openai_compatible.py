"""Base for any OpenAI-style `/chat/completions` API: Groq, OmniRoute, OpenAI,
OpenRouter, Together, Mistral, Ollama, vLLM, LM Studio...

A new provider of this kind only needs a subclass with `name` and `from_settings`.
"""

from app.ai.exceptions import ProviderError
from app.ai.providers.base import BaseLLMProvider
from app.ai.types import ChatMessage, LLMResponse, TokenUsage


class OpenAICompatibleProvider(BaseLLMProvider):
    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        model = model or self.model
        payload: dict = {"model": model, "messages": [m.model_dump() for m in messages]}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        data = await self._post_json("/chat/completions", payload, headers)

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(self.name, f"unexpected response shape: {str(data)[:300]}") from exc
        if not text.strip():
            finish = data["choices"][0].get("finish_reason")
            raise ProviderError(self.name, f"empty response (finish_reason={finish})")

        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("model") or model,
            usage=TokenUsage(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            ),
            raw=data,
        )
