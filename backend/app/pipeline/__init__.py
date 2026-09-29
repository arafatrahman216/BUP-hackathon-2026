"""Tick pipeline: read -> validate -> save -> detect -> predict -> decide -> explain -> post.

The stages here are hard-coded rules (baseline). To integrate a model, write a class
with the same method (`predict(world)`, `plan(world, forecasts, skip)`, or
`explain(plan, forecast, world)`) and return it from the matching builder below.
The rule-based versions stay as the fallback.
"""

from app.core.config import Settings
from app.pipeline.decide import Planner, RulePlanner
from app.pipeline.explain import TemplateExplainer
from app.pipeline.predict import MovingAveragePredictor, Predictor


def build_predictor(settings: Settings) -> Predictor:
    return MovingAveragePredictor(settings.FORECAST_WINDOW_TICKS, settings.SAFETY_TICKS, settings.URGENT_MARGIN_TICKS)


def build_planner(settings: Settings) -> Planner:
    return RulePlanner(settings.MIN_SHIPMENT_LITERS, settings.DEPOT_RESERVE_LITERS)


def build_fallback_planner(settings: Settings) -> Planner:
    return RulePlanner(settings.MIN_SHIPMENT_LITERS, settings.DEPOT_RESERVE_LITERS)


def build_explainer(settings: Settings) -> TemplateExplainer:
    return TemplateExplainer()
