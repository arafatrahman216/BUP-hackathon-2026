from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.registry import register_provider
from app.core.config import Settings


@register_provider
class OmniRouteProvider(OpenAICompatibleProvider):
    """OmniRoute gateway (OpenAI-compatible). Usually self-hosted, so the API key is optional."""

    name = "omniroute"

    @classmethod
    def from_settings(cls, settings: Settings) -> "OmniRouteProvider":
        return cls(
            api_key=settings.OMNIROUTE_API_KEY,
            model=settings.OMNIROUTE_MODEL,
            base_url=settings.OMNIROUTE_BASE_URL,
            timeout=settings.AI_TIMEOUT_SECONDS,
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.model)
