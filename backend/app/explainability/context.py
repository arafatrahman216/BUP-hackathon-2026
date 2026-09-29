"""Profiles (which metrics go to the LLM) and context building (metrics -> one JSON dict)."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.explainability.metrics import METRICS
from app.explainability.types import MetricContext

DEFAULT_PROFILES_PATH = Path(__file__).with_name("profiles.json")


@dataclass
class Profile:
    name: str
    description: str
    metrics: list[str]
    instructions: str = ""
    suggested_questions: dict[str, list[str]] = field(default_factory=dict)  # by action status, "default"

    def suggestions(self, status: str | None) -> list[str]:
        return self.suggested_questions.get(status or "", self.suggested_questions.get("default", []))


@dataclass
class ProfileBook:
    default_profile: str
    profiles: dict[str, Profile]
    params: dict[str, Any] = field(default_factory=dict)


def load_profiles(path: str | Path | None = None) -> ProfileBook:
    """Read on every call, so edits to the JSON apply without a restart."""
    raw = json.loads(Path(path or DEFAULT_PROFILES_PATH).read_text(encoding="utf-8"))
    profiles = {
        name: Profile(name, p.get("description", ""), list(p.get("metrics", [])), p.get("instructions", ""),
                      dict(p.get("suggested_questions", {})))
        for name, p in raw.get("profiles", {}).items()
    }
    return ProfileBook(raw.get("default_profile") or next(iter(profiles), ""), profiles, dict(raw.get("params", {})))


def unknown_metrics(names: list[str]) -> list[str]:
    return [n for n in names if n not in METRICS]


@dataclass
class BuiltContext:
    context: dict[str, Any]  # what the LLM sees
    errors: list[dict[str, str]]  # metrics that could not be computed


def build_context(names: list[str], ctx: MetricContext, notes: list[str] | None = None) -> BuiltContext:
    """Runs each metric. One that raises is reported in `errors` (and in the context's
    `_unavailable`) instead of failing the request. `notes` explain degraded inputs."""
    context: dict[str, Any] = {"_meta": {
        "subject": ctx.subject.ids(), "stale_data": ctx.world.stale, "data_source": ctx.snapshot.source,
    }}
    if notes:
        context["_meta"]["notes"] = notes
    errors: list[dict[str, str]] = []
    for name in names:
        try:
            value = METRICS[name].fn(ctx)
        except Exception as exc:  # a broken metric must not break the answer
            errors.append({"metric": name, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if value is not None:
            context[name] = value
    if errors:
        context["_unavailable"] = [e["metric"] for e in errors]
    return BuiltContext(context, errors)
