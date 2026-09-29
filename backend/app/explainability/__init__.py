"""Explainability: answer operator questions with an LLM, grounded in the pipeline's data.

    question + subject (a recommendation / allocation / station / depot ...)
      -> profile (profiles.json) picks the metrics
      -> snapshot: the pipeline's cached world + predict (forecasts) + detect (alerts),
         or a live read through the same stages when there is no cache yet
      -> metrics.py turns it into one JSON context
      -> prompt.py -> LLM (Gemini first) -> answer (stored per recommendation)

To change what the LLM sees, edit `profiles.json` (which metrics per profile, params,
suggested questions) or add a metric in `metrics.py`.
"""

from app.explainability.context import BuiltContext, Profile, ProfileBook, build_context, load_profiles
from app.explainability.metrics import METRICS, MetricSpec, metric
from app.explainability.prompt import SYSTEM_PROMPT, build_messages
from app.explainability.types import MetricContext, Snapshot, Subject

__all__ = [
    "METRICS", "SYSTEM_PROMPT", "BuiltContext", "MetricContext", "MetricSpec", "Profile", "ProfileBook",
    "Snapshot", "Subject", "build_context", "build_messages", "load_profiles", "metric",
]
