from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: Role
    content: str


class TokenUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ProviderAttempt(BaseModel):
    """One step of the fallback chain, returned so callers can see what happened."""

    provider: str
    model: str | None = None
    status: Literal["success", "failed", "skipped"]
    error: str | None = None
    latency_ms: float | None = None


class LLMResponse(BaseModel):
    text: str
    provider: str
    model: str
    usage: TokenUsage | None = None
    attempts: list[ProviderAttempt] = Field(default_factory=list)
    raw: dict[str, Any] | None = Field(default=None, exclude=True)
