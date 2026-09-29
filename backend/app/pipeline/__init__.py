"""Tick pipeline: read -> validate -> save -> detect -> predict -> decide -> explain -> post.

Intelligence (intelligence-plan.md §0.1), chosen by PREDICTOR / PLANNER settings:
- predict: StructuralPredictor (structural demand model + deterministic simulator copy);
  baseline MovingAveragePredictor
- decide:  OptimizerPlanner (strategic LP + tactical MIP-MPC); RulePlanner (priority greedy +
  reorder point) is the baseline and always the fallback
Stateful parts (demand model, detector) live in PipelineState so they survive between ticks.
"""

from app.core.config import Settings
from app.pipeline.decide import Planner, RulePlanner
from app.pipeline.demand_model import DemandModel
from app.pipeline.detect import Detector
from app.pipeline.explain import TemplateExplainer
from app.pipeline.predict import MovingAveragePredictor, Predictor, StructuralPredictor


def ensure_models(state, settings: Settings) -> None:
    if state.demand_model is None:
        state.demand_model = DemandModel()
    if state.detector is None:
        state.detector = Detector(settings.ANOMALY_Z, settings.ANOMALY_CUSUM_K, settings.ANOMALY_CUSUM_H,
                                  settings.ANOMALY_MIN_LITERS)


def build_predictor(settings: Settings, state=None) -> Predictor:
    if settings.PREDICTOR == "structural" and state is not None:
        ensure_models(state, settings)
        return StructuralPredictor(state.demand_model, settings.FORECAST_HORIZON_TICKS, settings.SAFETY_TICKS,
                                   settings.URGENT_MARGIN_TICKS, settings.RATIONING_TRIGGER_DAYS)
    return MovingAveragePredictor(settings.FORECAST_WINDOW_TICKS, settings.SAFETY_TICKS, settings.URGENT_MARGIN_TICKS)


def build_planner(settings: Settings) -> Planner:
    if settings.PLANNER == "optimizer":
        from app.pipeline.optimizer import OptimizerPlanner

        return OptimizerPlanner(settings.FORECAST_HORIZON_TICKS, settings.MIN_SHIPMENT_LITERS,
                                settings.PLANNER_TIME_LIMIT_SECONDS, settings.RATIONING_TRIGGER_DAYS)
    return RulePlanner(settings.MIN_SHIPMENT_LITERS, settings.DEPOT_RESERVE_LITERS)


def build_fallback_planner(settings: Settings) -> Planner:
    return RulePlanner(settings.MIN_SHIPMENT_LITERS, settings.DEPOT_RESERVE_LITERS)


def build_explainer(settings: Settings) -> TemplateExplainer:
    return TemplateExplainer()
