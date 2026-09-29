"""Provider registry. Decorate a provider class with @register_provider to make it
usable by name in AI_PROVIDER_ORDER."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.providers.base import BaseLLMProvider

_PROVIDERS: dict[str, type["BaseLLMProvider"]] = {}


def register_provider(cls: type["BaseLLMProvider"]) -> type["BaseLLMProvider"]:
    _PROVIDERS[cls.name] = cls
    return cls


def get_provider_classes() -> dict[str, type["BaseLLMProvider"]]:
    # Importing the package runs every @register_provider decorator.
    import app.ai.providers  # noqa: F401

    return dict(_PROVIDERS)
