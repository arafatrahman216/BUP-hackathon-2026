from app.ai.types import ProviderAttempt


class AIError(Exception):
    """Base class for everything the AI module raises."""


class ProviderError(AIError):
    """A single provider call failed. The client catches this and falls back."""

    def __init__(self, provider: str, message: str, *, status_code: int | None = None) -> None:
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {message}")


class UnknownProviderError(AIError):
    def __init__(self, name: str, available: list[str]) -> None:
        super().__init__(f"Unknown AI provider '{name}'. Available: {', '.join(sorted(available))}")


class AllProvidersFailedError(AIError):
    def __init__(self, attempts: list[ProviderAttempt]) -> None:
        self.attempts = attempts
        super().__init__("All AI providers in the chain failed or were not configured")


class AIResponseParseError(AIError):
    """The model answered, but not in the format we asked for (e.g. invalid JSON)."""
