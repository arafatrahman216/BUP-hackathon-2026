from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ai.types import ProviderAttempt


class ContextRequest(BaseModel):
    """What to explain. Give an action (inline, a recommendation id or an allocation id)
    and/or subject ids; ids missing from the request are taken from the action."""

    profile: str | None = Field(None, description="Profile from profiles.json; default: its default_profile")
    metrics: list[str] | None = Field(None, description="Override the profile's metric list")
    params: dict[str, Any] | None = Field(None, description="Override metric params, e.g. {\"history_ticks\": 32}")
    action: dict[str, Any] | None = Field(None, description="Any action state to explain, sent as-is")
    recommendation_id: int | None = None
    allocation_id: int | None = None
    station_id: str | None = None
    fuel_type: str | None = None
    depot_id: str | None = None
    route_id: str | None = None


class ExplainRequest(ContextRequest):
    question: str = Field(min_length=1, max_length=2000)


class MetricError(BaseModel):
    metric: str
    error: str


class ContextResponse(BaseModel):
    profile: str
    metrics: list[str]
    data_source: str  # pipeline_cache | live
    tick: int
    context: dict[str, Any]  # the JSON the LLM receives
    errors: list[MetricError]


class ExplainResponse(ContextResponse):
    question: str
    answer: str
    provider: str
    model: str
    attempts: list[ProviderAttempt] = []


# --- questions about one recommendation (approval queue / decision log) ---

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ActionQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    recommendation_id: int
    tick: int | None
    question: str
    answer: str
    profile: str
    provider: str
    model: str
    context: dict[str, Any]
    errors: list[MetricError]
    created_at: datetime


class ActionQuestions(BaseModel):
    recommendation_id: int
    status: str
    suggestions: list[str]  # from profiles.json, by the recommendation's status
    items: list[ActionQuestionRead]  # newest first


# --- catalog ---

class MetricInfo(BaseModel):
    name: str
    description: str


class ProfileInfo(BaseModel):
    description: str
    metrics: list[str]
    instructions: str
    suggested_questions: dict[str, list[str]]


class ExplainCatalog(BaseModel):
    default_profile: str
    params: dict[str, Any]
    profiles: dict[str, ProfileInfo]
    metrics: list[MetricInfo]
