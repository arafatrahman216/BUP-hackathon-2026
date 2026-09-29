from abc import ABC, abstractmethod
from typing import Any, ClassVar, Self

import httpx

from app.ai.exceptions import ProviderError
from app.ai.types import ChatMessage, LLMResponse
from app.core.config import Settings


class BaseLLMProvider(ABC):
    """Contract every provider implements. Providers are stateless apart from a
    lazily-created HTTP client, and raise ProviderError on any failure."""

    name: ClassVar[str]

    def __init__(self, *, api_key: str, model: str, base_url: str, timeout: float = 60.0) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout = timeout
        self._http: httpx.AsyncClient | None = None

    @classmethod
    @abstractmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Build the provider from app settings."""

    @property
    def is_configured(self) -> bool:
        """Unconfigured providers are skipped in the fallback chain."""
        return bool(self.api_key and self.model)

    @abstractmethod
    async def generate(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        """Send a chat conversation and return the reply."""

    @property
    def http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _post_json(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            response = await self.http.post(path, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(self.name, f"timed out after {self.timeout}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"network error: {exc}") from exc

        if response.status_code >= 400:
            raise ProviderError(
                self.name,
                f"HTTP {response.status_code}: {response.text[:500]}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(self.name, "response was not valid JSON") from exc
