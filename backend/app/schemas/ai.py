from pydantic import BaseModel, Field, model_validator

from app.ai.types import ChatMessage


class GenerationParams(BaseModel):
    provider: str | None = Field(default=None, description="Call only this provider (skips the fallback chain)")
    model: str | None = Field(default=None, description="Model override; requires `provider`")
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=65536)
    json_mode: bool = False

    @model_validator(mode="after")
    def model_needs_provider(self):
        if self.model and not self.provider:
            raise ValueError("`model` can only be set together with `provider`")
        return self


class ChatRequest(GenerationParams):
    messages: list[ChatMessage] = Field(min_length=1)


class GenerateRequest(GenerationParams):
    prompt: str = Field(min_length=1)
    system: str | None = None


class ProviderInfo(BaseModel):
    name: str
    configured: bool
    default_model: str | None


class AIStatus(BaseModel):
    fallback_enabled: bool
    provider_order: list[str]
    active_chain: list[str]
    providers: list[ProviderInfo]
