from app.ai import LLMClient, LLMResponse
from app.schemas.ai import AIStatus, ChatRequest, GenerateRequest


class AIService:
    """Thin service over LLMClient for the generic /ai endpoints. Feature services
    should take an LLMClient directly and build their own prompts."""

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm

    async def chat(self, payload: ChatRequest) -> LLMResponse:
        return await self.llm.chat(payload.messages, **payload.model_dump(exclude={"messages"}))

    async def generate(self, payload: GenerateRequest) -> LLMResponse:
        return await self.llm.complete(payload.prompt, **payload.model_dump(exclude={"prompt"}))

    def status(self) -> AIStatus:
        return AIStatus.model_validate(self.llm.describe())
