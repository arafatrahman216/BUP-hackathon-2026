"""Google Gemini via the REST `generateContent` endpoint (no SDK dependency)."""

from app.ai.exceptions import ProviderError
from app.ai.providers.base import BaseLLMProvider
from app.ai.registry import register_provider
from app.ai.types import ChatMessage, LLMResponse, TokenUsage
from app.core.config import Settings


@register_provider
class GeminiProvider(BaseLLMProvider):
    name = "gemini"

    @classmethod
    def from_settings(cls, settings: Settings) -> "GeminiProvider":
        return cls(
            api_key=settings.GEMINI_API_KEY,
            model=settings.GEMINI_MODEL,
            base_url=settings.GEMINI_BASE_URL,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )

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

        # Gemini takes system prompts separately and calls the assistant role "model".
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        payload: dict = {
            "contents": [
                {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
                for m in messages
                if m.role != "system"
            ]
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        generation_config: dict = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_tokens is not None:
            # Note: on 2.5 "thinking" models this budget includes thinking tokens.
            generation_config["maxOutputTokens"] = max_tokens
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        if generation_config:
            payload["generationConfig"] = generation_config

        data = await self._post_json(
            f"/models/{model}:generateContent", payload, {"x-goog-api-key": self.api_key}
        )

        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise ProviderError(self.name, f"no response ({reason})")

        candidate = candidates[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text.strip():
            raise ProviderError(self.name, f"empty response (finishReason={candidate.get('finishReason')})")

        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=data.get("modelVersion") or model,
            usage=TokenUsage(
                prompt_tokens=usage.get("promptTokenCount"),
                completion_tokens=usage.get("candidatesTokenCount"),
                total_tokens=usage.get("totalTokenCount"),
            ),
            raw=data,
        )
