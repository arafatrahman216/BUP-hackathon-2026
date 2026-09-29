"""Fixed-format answer to "why does this need my approval?" on a pending card.

Demo script, not the LLM: it tells the "one depot, two stations" story with the card's real station,
depot, stock and quantity. The second station is the depot's most at-risk other station; when the depot
serves no other station, a made-up one stands in.
"""

import re
from typing import Any

PROVIDER, MODEL = "template", "approval-scenario"
FALLBACK_STATION = "Tongi Fuel Station"
_APPROVAL_QUESTION = re.compile(r"approv|manual|\bauto", re.IGNORECASE)


def is_approval_question(question: str) -> bool:
    return bool(_APPROVAL_QUESTION.search(question))


def _liters(x: float) -> str:
    return f"{x:,.0f} L"


def _short(name: str) -> str:
    return name.removesuffix(" Fuel Station").removesuffix(" Station")


def _next_ship(context: dict[str, Any]) -> str:
    clock = context.get("clock") or {}
    ships = sorted((s for s in context.get("supply") or [] if s.get("planned_tick") is not None),
                   key=lambda s: s["planned_tick"])
    if not ships or clock.get("tick") is None:
        return "the next ship is hours away"
    ticks = max(0, int(ships[0]["planned_tick"]) - int(clock["tick"]))
    hours = ticks * int(clock.get("tick_minutes") or 15) / 60
    return f"the next ship ({_liters(float(ships[0].get('quantity') or 0))}) is due in {ticks} ticks (~{hours:.1f} h)"


def _other_station(context: dict[str, Any], fuel: str, names: dict[str, str], subject: str) -> tuple[str, str]:
    rows = ((context.get("depot_stations") or {}).get(fuel) or {}).get("stations") or []
    others = [r for r in rows if not r.get("is_subject")]
    at_risk = [r for r in others if r.get("risk") in ("urgent", "watch")]
    pick = sorted(at_risk or others, key=lambda r: r.get("cover_ticks") if r.get("cover_ticks") is not None else 1e9)
    if pick:
        name = names.get(pick[0]["station_id"], pick[0]["station_id"])
        return name, pick[0]["risk"] if pick[0] in at_risk else "watch"
    return (FALLBACK_STATION if subject != FALLBACK_STATION else "Savar Fuel Station"), "watch"


def approval_answer(context: dict[str, Any], names: dict[str, str]) -> str:
    action = context.get("action") or {}
    fuel = action.get("fuel_type") or ""
    word = fuel.lower()
    station = (context.get("station") or {}).get("name") or names.get(action.get("station_id"), action.get("station_id"))
    depot_info = context.get("depot") or {}
    depot = depot_info.get("name") or action.get("depot_id")
    stock = float(((depot_info.get("fuels") or {}).get(fuel) or {}).get("inventory_l") or 0)
    qty = float(action.get("quantity") or 0)
    other, other_risk = _other_station(context, fuel, names, station)
    left = max(0.0, stock - qty)
    split = int(min(qty, (stock if stock > 0 else qty) / 2) // 100) * 100

    share = (f"That's {qty / stock:.0%} of the depot's stock, so it goes to you for approval." if stock > 0
             else "That is more than the depot has left, so it goes to you for approval.")
    lines = [
        '**"One depot, two stations running dry"**',
        f"* {depot} has {_liters(stock)} of {word} left, and {_next_ship(context)}.",
        f"* {_short(station)}'s {word} is {action.get('risk') or 'urgent'}, so the optimizer plans {_liters(qty)} for it. {share}",
        f'* {_short(other)} also runs on {depot} {word} and is on "{other_risk}". If you approve all {_liters(qty)}, '
        f"{_short(other)} will be dry within hours with {'nothing' if left < 100 else 'only ' + _liters(left)} left to send.",
        "Your options:",
        f"* approve it as it is (save {_short(station)} now)",
        f"* edit it down to about {_liters(split)} so both stations get something",
        "* reject it and wait for the ship",
    ]
    return "\n".join(lines)
