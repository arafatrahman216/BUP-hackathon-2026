"""Detect stage (rules): turn the current world into operator alerts."""

from app.pipeline.types import Alert, Forecast, World


def detect(world: World) -> list[Alert]:
    alerts: list[Alert] = []
    for station_id, station in world.stations.items():
        if station.get("status") != "OPEN":
            alerts.append(Alert("critical", "STATION_OUTAGE", f"{station.get('name', station_id)} is in {station.get('status')}", station_id))
        multiplier = float(station.get("demand_multiplier") or 1.0)
        if multiplier != 1.0:
            alerts.append(Alert("warning", "DEMAND_SPIKE", f"{station.get('name', station_id)} demand x{multiplier:g}", station_id))
    for route_id, route in world.routes.items():
        if route.get("status") != "AVAILABLE":
            alerts.append(Alert("critical", "ROUTE_DISRUPTED", f"Route {route_id} is {route.get('status')}", route_id))
    for depot_id, depot in world.depots.items():
        if depot.get("status") != "OPEN":
            alerts.append(Alert("warning", "DEPOT_CONSTRAINED", f"{depot.get('name', depot_id)} is {depot.get('status')}", depot_id))
    for event in world.events:
        if event.get("status") == "ACTIVE":
            alerts.append(Alert("critical", "CRISIS_ACTIVE", f"{event.get('type')} active until tick {event.get('end_tick')}", str(event.get("id"))))
        elif event.get("status") == "SCHEDULED":
            alerts.append(Alert("info", "CRISIS_SCHEDULED", f"{event.get('type')} starts at tick {event.get('start_tick')}", str(event.get("id"))))
    for arrival in world.supply:
        if arrival.get("status") == "DELAYED":
            alerts.append(Alert("warning", "SUPPLY_DELAYED", f"{arrival.get('depot_id')} {arrival.get('fuel_type')} ship delayed to tick {arrival.get('planned_tick')}", arrival.get("id")))
    for allocation in world.allocations[:50]:
        if allocation.get("status") == "FAILED" and allocation.get("created_tick", 0) >= world.tick - 8:
            alerts.append(Alert("critical", "SHIPMENT_FAILED", f"Allocation {allocation.get('id')} failed: {allocation.get('failure_reason')}", str(allocation.get("id"))))

    last_tick = max((row.get("tick", 0) for row in world.history), default=None)
    unmet = sum(float(r.get("unmet_liters") or 0) for r in world.history if r.get("tick") == last_tick)
    if unmet > 0:
        alerts.append(Alert("warning", "UNMET_DEMAND", f"{unmet:,.0f} L of demand went unserved at tick {last_tick}"))
    return alerts


def stockout_alerts(forecasts: dict[tuple[str, str], Forecast]) -> list[Alert]:
    """Predict-stage alerts: station/fuels whose cover is below lead time + urgent margin."""
    return [
        Alert("critical", "STOCKOUT_RISK", f"{f.station_id} {f.fuel_type} covers {f.cover_ticks:.1f} ticks, "
              f"lead time {f.lead_ticks} ticks", f.station_id)
        for f in forecasts.values() if f.risk == "urgent"
    ]
