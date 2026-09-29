"""Explain stage: a plain-language reason for each recommendation.

Baseline is a fixed template (no LLM). An LLM explainer can wrap this and fall back to it.
"""

from app.pipeline.types import Forecast, Plan, World


def _hours(ticks: float | None, tick_minutes: int) -> str:
    if ticks is None:
        return "no measurable demand"
    return f"{ticks:.1f} ticks (~{ticks * tick_minutes / 60:.1f} h)"


class TemplateExplainer:
    name = "template"

    def explain(self, plan: Plan, forecast: Forecast, world: World) -> str:
        station = world.stations[plan.station_id]
        depot = world.depots[plan.depot_id]
        route = world.routes[plan.route_id]
        rate = forecast.rate_per_tick or 0
        text = (
            f"{station.get('name', plan.station_id)} {plan.fuel_type} holds {forecast.inventory:,.0f} of "
            f"{forecast.capacity:,.0f} L and uses about {rate:,.0f} L per tick, so it empties in "
            f"{_hours(forecast.ticks_until_empty, world.tick_minutes)}"
        )
        if forecast.incoming:
            text += f"; {forecast.incoming:,.0f} L is already on the way (covers {_hours(forecast.cover_ticks, world.tick_minutes)})"
        text += (
            f". Risk is {forecast.risk.upper()}. Send {plan.quantity:,.0f} L from {depot.get('name', plan.depot_id)} "
            f"({float(depot['inventory'].get(plan.fuel_type, 0)):,.0f} L in stock) via {plan.route_id}, "
            f"arriving in {route['transit_ticks']} ticks."
        )
        if plan.reasons:
            text += " Needs operator review: " + "; ".join(plan.reasons) + "."
        return text
