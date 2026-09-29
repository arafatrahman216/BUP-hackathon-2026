"""Structural predictor, simulator copy, detector and optimizer (intelligence-plan.md §0.1)."""

import pytest

from app.core.config import get_settings
from app.pipeline.demand_model import DemandModel, prior_hour_factor
from app.pipeline.detect import Detector
from app.pipeline.optimizer import OptimizerPlanner
from app.pipeline.predict import StructuralPredictor
from app.pipeline.twin import Shipment, project
from app.pipeline.types import World
from tests.fake_simulator import base_world


def make_world(**changes) -> World:
    w = base_world()
    for st in w["stations"]:
        st.update(changes.get(st["id"], {}))
    return World(
        instance=w["instance"], depots={d["id"]: d for d in w["depots"]},
        stations={s["id"]: s for s in w["stations"]}, routes={r["id"]: r for r in w["routes"]},
        supply=changes.get("supply", []), events=changes.get("events", []), allocations=changes.get("allocations", []),
        history=changes.get("history", []), metrics={},
    )


def history_rows(world: World, ticks: range, scale: float = 1.0) -> list[dict]:
    """Demand that follows the published pattern exactly (tick 0 = 00:00)."""
    rows = []
    daily = {"urban_high": {"DIESEL": 8500, "PETROL": 10500}, "industrial": {"DIESEL": 14000, "PETROL": 4500}}
    for t in ticks:
        hour = (t * 15 // 60) % 24
        for sid, st in world.stations.items():
            for f in ("DIESEL", "PETROL"):
                d = daily[st["demand_profile"]][f] / 96 * prior_hour_factor(st["demand_profile"], hour) * scale
                rows.append({"station_id": sid, "fuel_type": f, "tick": t, "demand_liters": d,
                             "served_liters": d, "unmet_liters": 0.0})
    return rows


def predictor(model=None) -> StructuralPredictor:
    return StructuralPredictor(model or DemandModel(), 24, 8, 2, 3.0)


def test_demand_model_learns_a_new_level_and_keeps_the_time_of_day_shape():
    world = make_world()
    world.history = history_rows(world, range(0, 100), scale=1.3)  # 30% above the published tables
    model = DemandModel()
    model.ingest(world)
    level = model.level_of("station-tongi", "DIESEL")
    assert level == pytest.approx(14000 / 96 * 1.3, rel=0.12)
    # industrial: busy 06-18 (1.55) vs night (0.45) -> the shape survives learning
    assert model.shape_of("station-tongi", 10) / model.shape_of("station-tongi", 2) == pytest.approx(1.55 / 0.45, rel=0.15)


def test_forecast_includes_a_scheduled_spike():
    spike = {"id": 7, "type": "demand_spike", "status": "SCHEDULED", "start_tick": 105, "end_tick": 110,
             "parameters": {"station_ids": ["station-mirpur"], "multiplier": 2.0}}
    world = make_world(events=[spike])
    model = DemandModel()
    model.ingest(world)
    path = model.path(world, "station-mirpur", "DIESEL", 12)
    assert path[6] == pytest.approx(path[2] * 2 * prior_hour_factor("urban_high", 2) / prior_hour_factor("urban_high", 1), rel=0.01) \
        or path[6] > path[4] * 1.5


def test_simulator_copy_counts_tank_overflow_and_stockout():
    world = make_world(**{"station-tongi": {"inventory": {"DIESEL": 17000, "PETROL": 300}}})
    flat = lambda s, f, k: 100.0  # noqa: E731
    proj = project(world, flat, 10, [Shipment(0, "route-gazipur-tongi", "DIESEL", 6500)])
    tongi = proj.stations[("station-tongi", "DIESEL")]
    assert tongi.tank_overflow == pytest.approx(17000 - 200 + 6500 - 18000)  # 2 ticks of demand before landing
    assert proj.stations[("station-tongi", "PETROL")].stockout_k == 3


def test_predictor_gives_time_until_empty_risk_and_outlook():
    world = make_world(**{"station-mirpur": {"inventory": {"DIESEL": 400, "PETROL": 9000}}})
    p = predictor()
    p.model.ingest(world)
    forecasts = p.predict(world)
    f = forecasts[("station-mirpur", "DIESEL")]
    assert f.risk in ("watch", "urgent") and f.p_stockout > 0.9 and f.unmet_horizon > 0 and f.order_by_tick is not None
    assert len(f.demand_path) == 24 and f.naive_ticks_until_empty is not None
    assert p.outlook["fuels"]["DIESEL"]["rationing"] is True  # no ships left in this world
    assert p.outlook["do_nothing"]["unmet_liters"] > 0


def test_optimizer_ships_within_every_rule():
    world = make_world(**{"station-mirpur": {"inventory": {"DIESEL": 400, "PETROL": 9000}},
                          "station-tongi": {"inventory": {"DIESEL": 300, "PETROL": 6000}}})
    world.depots["depot-gazipur"]["dispatch_capacity_per_tick"] = 9000
    p = predictor()
    p.model.ingest(world)
    forecasts = p.predict(world)
    plans, blocked = OptimizerPlanner(24, 500, 5, 3.0).plan(world, forecasts, set())
    assert plans, blocked
    per_depot = {}
    for plan in plans:
        route = world.routes[plan.route_id]
        assert route["source_depot_id"] == plan.depot_id and route["destination_station_id"] == plan.station_id
        assert 500 <= plan.quantity <= route["max_shipment"]
        station = world.stations[plan.station_id]
        assert station["inventory"][plan.fuel_type] + plan.quantity <= station["capacity"][plan.fuel_type]
        per_depot[plan.depot_id] = per_depot.get(plan.depot_id, 0) + plan.quantity
        assert plan.impact["unmet_after"] <= plan.impact["unmet_before"]
    assert per_depot.get("depot-gazipur", 0) <= 9000
    assert {(p.station_id, p.fuel_type) for p in plans} >= {("station-mirpur", "DIESEL"), ("station-tongi", "DIESEL")}


def test_optimizer_avoids_a_cut_road():
    world = make_world(**{"station-mirpur": {"inventory": {"DIESEL": 400, "PETROL": 9000}}})
    world.routes["route-gazipur-mirpur"]["status"] = "DISRUPTED"
    p = predictor()
    p.model.ingest(world)
    plans, _ = OptimizerPlanner(24, 500, 5, 3.0).plan(world, p.predict(world), set())
    mirpur = [pl for pl in plans if pl.station_id == "station-mirpur"]
    assert mirpur and all(pl.route_id == "route-patiya-mirpur" for pl in mirpur)


def test_detector_changes_single_route_and_incidents():
    world = make_world()
    world.routes["route-gazipur-tongi"]["status"] = "DISRUPTED"
    world.events = [{"id": 3, "type": "route_disruption", "status": "ACTIVE", "start_tick": 99, "end_tick": 110,
                     "parameters": {"route_ids": ["route-gazipur-tongi"]}}]
    det = Detector()
    alerts = det.detect(world)
    codes = {a.code for a in alerts}
    assert {"ROUTE_DISRUPTED", "SINGLE_ROUTE_CUT", "CRISIS_ACTIVE"} <= codes
    cut = next(a for a in alerts if a.code == "SINGLE_ROUTE_CUT")
    assert cut.explained_by == "event 3 (route_disruption)" and cut.since_tick == 100
    assert det.incidents[0]["status"] == "open" and det.incidents[0]["region_id"] == "region-dhaka"

    world2 = make_world()
    world2.instance = {**world2.instance, "tick": 101}
    det.detect(world2)
    assert det.incidents[0]["status"] == "resolved"


def test_detector_flags_unexplained_demand_jump():
    world = make_world()
    model, det = DemandModel(), Detector()
    world.history = history_rows(world, range(0, 96))
    model.ingest(world)
    jump = make_world()
    jump.history = history_rows(jump, range(96, 100), scale=1.8)
    alerts = det.detect(jump, model.ingest(jump))
    anomaly = [a for a in alerts if a.code == "DEMAND_ANOMALY"]
    assert anomaly and anomaly[0].explained_by == "unexplained"


def test_supply_shortfall_and_delay_vs_first_seen():
    ship = {"id": "s1", "depot_id": "depot-gazipur", "fuel_type": "DIESEL", "quantity": 18000, "planned_tick": 120,
            "status": "SCHEDULED"}
    det = Detector()
    det.detect(make_world(supply=[ship]))
    alerts = det.detect(make_world(supply=[{**ship, "quantity": 9000, "planned_tick": 124, "status": "DELAYED"}]))
    assert {"SUPPLY_SHORTFALL", "SUPPLY_DELAYED"} <= {a.code for a in alerts}



@pytest.mark.anyio
async def test_pipeline_end_to_end_with_structural_and_optimizer(client, fake_sim, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "PREDICTOR", "structural")
    monkeypatch.setattr(settings, "PLANNER", "optimizer")
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 300  # ~3 ticks left
    assert (await client.post("/api/v1/pipeline/run")).status_code == 200
    state = (await client.get("/api/v1/dashboard")).json()
    stages = {s["name"]: s["status"] for s in state["pipeline"]["stages"]}
    assert stages["predict"] == "ok" and stages["decide"] == "ok", state["pipeline"]["stages"]
    tongi = next(s for s in state["stations"] if s["id"] == "station-tongi")
    diesel = next(f for f in tongi["fuels"] if f["fuel_type"] == "DIESEL")
    assert diesel["source"] == "structural" and diesel["p_stockout"] is not None
    assert state["outlook"]["planner"]["planner"] == "optimizer"
    recs = state["recommendations"]["open"] + state["recommendations"]["recent"]
    tongi_recs = [r for r in recs if r["station_id"] == "station-tongi" and r["fuel_type"] == "DIESEL"]
    assert tongi_recs and tongi_recs[0]["planner"] == "optimizer" and "Simulator copy" in tongi_recs[0]["explanation"]
