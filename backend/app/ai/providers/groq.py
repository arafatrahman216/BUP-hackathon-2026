from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.registry import register_provider
from app.core.config import Settings


@register_provider
class GroqProvider(OpenAICompatibleProvider):
    name = "groq"

    @classmethod
    def from_settings(cls, settings: Settings) -> "GroqProvider":
        return cls(
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
            base_url=settings.GROQ_BASE_URL,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )
