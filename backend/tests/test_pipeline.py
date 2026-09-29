import re

import pytest
from app.core.config import get_settings

from app.core.config import get_settings
from app.pipeline.decide import RulePlanner, recheck
from app.pipeline.predict import MovingAveragePredictor
from app.pipeline.state import get_pipeline_state
from app.pipeline.types import World
from app.repositories.simulator_repository import CircuitBreaker
from app.services.dashboard_service import DashboardService
from tests.fake_simulator import FakeSimulator

pytestmark = pytest.mark.anyio

# Defaults: rate 100 L/tick, lead 2 ticks, SAFETY_TICKS 8, URGENT_MARGIN 2
#   cover < 4 -> urgent, cover < 10 -> watch, else safe. Both are auto-posted on the fastest road;
#   tests of the approval flow use `manual_approval` (auto-post off) to get an operator card.


async def run(client) -> dict:
    response = await client.post("/api/v1/pipeline/run")
    assert response.status_code == 200, response.text
    return (await client.get("/api/v1/dashboard")).json()


def stage_status(state: dict) -> dict:
    return {s["name"]: s["status"] for s in state["pipeline"]["stages"]}


async def test_quiet_world_posts_nothing(client, fake_sim):
    state = await run(client)
    assert stage_status(state) == {n: "ok" for n in
                                   ("read", "validate", "save", "detect", "predict", "decide", "explain", "post")}
    assert state["sim"]["tick"] == 100 and state["sim"]["stale"] is False
    risks = {(s["id"], f["fuel_type"]): f["risk"] for s in state["stations"] for f in s["fuels"]}
    assert set(risks.values()) == {"safe"}
    assert fake_sim.posts == []
    snapshots = (await client.get("/api/v1/snapshots")).json()
    assert snapshots["total"] == 1 and snapshots["items"][0]["tick"] == 100


async def test_watch_risk_is_auto_posted(client, fake_sim):
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800  # cover 8 ticks -> watch
    state = await run(client)
    (post,) = fake_sim.posts
    assert re.fullmatch(r"bup-[0-9a-f]{12}-station-tongi-diesel-6500", post.pop("idempotency_key"))
    assert post == {
        "source_depot_id": "depot-gazipur", "destination_station_id": "station-tongi",
        "route_id": "route-gazipur-tongi", "fuel_type": "DIESEL", "quantity": 6500.0,
    }
    rec = state["recommendations"]["recent"][0]
    assert rec["status"] == "POSTED" and rec["decision_mode"] == "auto" and rec["allocation_id"] == 1
    assert "Tongi DIESEL holds 800" in rec["explanation"]

    # next tick: the shipment is incoming, so nothing new is planned
    fake_sim.world["instance"]["tick"] = 101
    await run(client)
    assert len(fake_sim.posts) == 1


async def test_urgent_on_fastest_road_is_auto_posted(client, fake_sim):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300  # cover 3 ticks -> urgent
    state = await run(client)
    rec = state["recommendations"]["recent"][0]
    assert rec["risk"] == "urgent" and rec["reasons"] == []
    assert rec["status"] == "POSTED" and rec["decision_mode"] == "auto"
    assert fake_sim.posts[0]["route_id"] == "route-gazipur-mirpur"


async def test_urgent_that_arrives_too_late_is_still_auto_posted(client, fake_sim):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 0  # already empty, truck needs 2 ticks
    rec = (await run(client))["recommendations"]["recent"][0]
    assert rec["status"] == "POSTED" and rec["reasons"] == [] and len(fake_sim.posts) == 1


async def test_urgent_that_drains_the_depot_needs_operator(client, fake_sim):
    fake_sim.world["depots"][0]["inventory"]["PETROL"] = 8000
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300  # arrives in time, but 7,000 of 8,000 L
    (rec,) = (await run(client))["recommendations"]["open"]
    assert rec["status"] == "PENDING_APPROVAL" and fake_sim.posts == []
    assert rec["reasons"] == ["urgent: takes 88% of depot-gazipur's PETROL stock (8,000 L)"]


@pytest.fixture
def risk_review(monkeypatch):
    monkeypatch.setattr(get_settings(), "REVIEW_RISK_ENABLED", True)


async def test_half_empty_tank_emptying_soon_needs_operator(client, fake_sim, risk_review):
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800  # 4% full, empty in 8 ticks, truck needs 2
    (rec,) = (await run(client))["recommendations"]["open"]
    assert rec["status"] == "PENDING_APPROVAL" and fake_sim.posts == []
    assert rec["reasons"] == ["tank at 4% (800 / 18,000 L), burning 100 L/tick: empty in ~8.0 ticks without a delivery"]


async def test_fast_drain_needs_operator(client, fake_sim, risk_review):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300  # empty in 3 ticks, truck needs 2
    (rec,) = (await run(client))["recommendations"]["open"]
    assert rec["status"] == "PENDING_APPROVAL"
    assert "fast drain: empty in ~3.0 ticks, fastest truck needs 2 (only 1.0 ticks to spare)" in rec["reasons"]


def test_risk_reasons_use_stockout_probability_and_shipment_impact():
    from app.pipeline.decide import ReviewRules, _risk_reasons
    from app.pipeline.types import Forecast, Plan
    f = Forecast("s", "DIESEL", inventory=9000, capacity=10000, rate_per_tick=100, incoming=0,
                 ticks_until_empty=90, cover_ticks=90, lead_ticks=2, risk="watch", p_stockout=0.45)
    plan = Plan("s", "DIESEL", "d", "r", 5000, "watch", 90,
                impact={"unmet_before": 1200, "unmet_after": 400})
    assert _risk_reasons(plan, f, ReviewRules()) == [
        "stockout risk 45% within the forecast horizon (threshold 30%)",
        "not enough: even with this shipment ~400 L stay unserved (vs ~1,200 L without it)",
    ]
    f.p_stockout, plan.impact = 0.1, {}
    assert _risk_reasons(plan, f, ReviewRules()) == []  # 90% full, safe -> auto
    assert _risk_reasons(plan, f, ReviewRules(enabled=False)) == []


async def test_operator_edits_and_approves(client, fake_sim, manual_approval):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300  # cover 3 ticks -> urgent
    state = await run(client)
    assert fake_sim.posts == []
    (rec,) = state["recommendations"]["open"]
    assert rec["status"] == "PENDING_APPROVAL" and rec["important"] and rec["risk"] == "urgent"
    assert rec["reasons"] == ["auto-post is disabled"]

    too_big = await client.post(f"/api/v1/recommendations/{rec['id']}/approve", json={"quantity": 9000})
    assert too_big.status_code == 400 and too_big.json()["error"]["code"] == "QUANTITY_TOO_LARGE"

    approved = (await client.post(f"/api/v1/recommendations/{rec['id']}/approve",
                                  json={"quantity": 5000, "note": "keep some room"})).json()
    assert approved["status"] == "POSTED" and approved["quantity"] == 5000 and approved["proposed_quantity"] == 7000
    assert fake_sim.posts[0]["quantity"] == 5000 and fake_sim.posts[0]["idempotency_key"].endswith("-5000")

    again = await client.post(f"/api/v1/recommendations/{rec['id']}/approve", json={})
    assert again.status_code == 409 and again.json()["error"]["code"] == "NOT_PENDING_APPROVAL"


async def test_reject(client, fake_sim, manual_approval):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300
    rec = (await run(client))["recommendations"]["open"][0]
    rejected = (await client.post(f"/api/v1/recommendations/{rec['id']}/reject", json={"note": "no"})).json()
    assert rejected["status"] == "REJECTED" and rejected["operator_note"] == "no"
    assert fake_sim.posts == []
    listed = (await client.get("/api/v1/recommendations", params={"status": "REJECTED"})).json()
    assert listed["total"] == 1


async def test_disrupted_route_uses_backup_and_asks_operator(client, fake_sim):
    fake_sim.route("route-gazipur-mirpur")["status"] = "DISRUPTED"
    fake_sim.station("station-mirpur")["inventory"]["DIESEL"] = 1000  # cover 10 < lead 4 + 8 -> watch
    state = await run(client)
    (rec,) = state["recommendations"]["open"]
    assert rec["route_id"] == "route-patiya-mirpur" and rec["quantity"] == 5000
    assert any("backup route" in r for r in rec["reasons"])
    assert "ROUTE_DISRUPTED" in {a["code"] for a in state["alerts"]}


async def test_active_crisis_makes_it_important(client, fake_sim):
    fake_sim.world["events"] = [{"id": 7, "type": "demand_spike", "status": "ACTIVE", "start_tick": 90,
                                 "end_tick": 120, "parameters": {"station_ids": ["station-tongi"], "multiplier": 2}}]
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800
    rec = (await run(client))["recommendations"]["open"][0]
    assert rec["status"] == "PENDING_APPROVAL" and any("demand_spike" in r for r in rec["reasons"])


async def test_simulator_refusal_is_recorded(client, fake_sim):
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800
    fake_sim.refuse = "INSUFFICIENT_INVENTORY"
    rec = (await run(client))["recommendations"]["recent"][0]
    assert rec["status"] == "REFUSED" and rec["error_code"] == "INSUFFICIENT_INVENTORY"


async def test_dispatch_limit_refusal_waits_for_next_tick(client, fake_sim):
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800
    fake_sim.refuse = "DISPATCH_CAPACITY_EXCEEDED"
    rec = (await run(client))["recommendations"]["open"][0]
    assert rec["status"] == "APPROVED" and rec["error_code"] == "DISPATCH_CAPACITY_EXCEEDED"

    fake_sim.refuse = None
    fake_sim.world["instance"]["tick"] = 101
    rec = (await run(client))["recommendations"]["recent"][0]
    assert rec["status"] == "POSTED" and len(fake_sim.posts) == 1


async def test_simulator_down_keeps_cached_state(client, fake_sim):
    await run(client)
    fake_sim.down = True
    state = await run(client)
    assert state["sim"]["connected"] is False and state["sim"]["stale"] is True
    assert state["sim"]["tick"] == 100 and len(state["stations"]) == 2  # cached
    assert stage_status(state)["read"] == "error" and stage_status(state)["post"] == "skipped"
    assert state["alerts"][0]["code"] == "SIMULATOR_UNREACHABLE"

    # an approved recommendation waits while the simulator is down, and posts when it comes back
    fake_sim.down = False
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800
    fake_sim.refuse = None
    await run(client)
    assert len(fake_sim.posts) == 1


async def test_stale_data_acts_cautiously(client, fake_sim):
    fake_sim.stale = True
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800  # watch: left alone on stale data
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300  # urgent: planned, halved
    state = await run(client)
    assert state["pipeline"]["acting"] is True and state["pipeline"]["cautious"] is True
    assert stage_status(state)["validate"] == "fallback" and stage_status(state)["decide"] == "ok"
    (rec,) = state["recommendations"]["open"]
    assert (rec["station_id"], rec["fuel_type"], rec["quantity"]) == ("station-mirpur", "PETROL", 3500)
    assert rec["status"] == "PENDING_APPROVAL" and any("stale" in r for r in rec["reasons"])

    # the operator approves without editing: stale data may shrink the shipment, never grow it
    approved = (await client.post(f"/api/v1/recommendations/{rec['id']}/approve", json={})).json()
    assert approved["status"] == "POSTED" and fake_sim.posts[0]["quantity"] == 3500


async def test_stale_data_mode_stop(client, fake_sim, monkeypatch):
    monkeypatch.setattr(get_settings(), "STALE_DATA_MODE", "stop")
    fake_sim.stale = True
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300
    state = await run(client)
    assert state["pipeline"]["acting"] is False and state["pipeline"]["cautious"] is False
    assert stage_status(state)["decide"] == "skipped" and state["recommendations"]["open"] == []


async def test_stale_data_skips_station_we_just_shipped_to(client, fake_sim):
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800
    await run(client)
    assert len(fake_sim.posts) == 1

    # stale data that doesn't show our shipment yet, and the tank looks almost empty
    fake_sim.stale = True
    fake_sim.world["allocations"] = []
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 300
    fake_sim.world["instance"]["tick"] = 101
    state = await run(client)
    assert state["recommendations"]["open"] == [] and len(fake_sim.posts) == 1


async def test_approval_is_refitted_to_the_current_world(client, fake_sim, manual_approval):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 800  # 8 ticks of fuel: the card may wait
    rec = (await run(client))["recommendations"]["open"][0]
    assert rec["quantity"] == 7000

    # while the operator reads it, the depot runs low
    fake_sim.world["depots"][0]["inventory"]["PETROL"] = 3050
    fake_sim.world["instance"]["tick"] = 101
    await run(client)
    approved = (await client.post(f"/api/v1/recommendations/{rec['id']}/approve", json={})).json()
    assert approved["status"] == "POSTED" and approved["quantity"] == 3000 and approved["proposed_quantity"] == 7000
    assert fake_sim.posts[0]["quantity"] == 3000 and fake_sim.posts[0]["idempotency_key"].endswith("-3000")
    assert "Resized from 7,000 to 3,000 L at tick 101" in approved["explanation"]


async def test_approval_of_a_plan_whose_route_was_cut_is_refused_locally(client, fake_sim, manual_approval):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300
    rec = (await run(client))["recommendations"]["open"][0]
    fake_sim.route("route-gazipur-mirpur")["status"] = "DISRUPTED"
    fake_sim.world["instance"]["tick"] = 101
    await run(client)
    refused = (await client.post(f"/api/v1/recommendations/{rec['id']}/approve", json={})).json()
    assert refused["status"] == "REFUSED" and refused["error_code"] == "ROUTE_DISRUPTED"
    assert fake_sim.posts == []  # never sent


async def test_lost_post_answer_is_reconciled_by_key(client, fake_sim):
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800
    fake_sim.lose_answer = True  # the allocation is created, but we only see a 503
    rec = (await run(client))["recommendations"]["open"][0]
    assert rec["status"] == "APPROVED" and rec["error_code"] == "FAULT_INJECTED"

    # next tick the tank looks different, but the earlier attempt is found by its key: no second shipment
    fake_sim.lose_answer = False
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 500
    fake_sim.world["instance"]["tick"] = 101
    rec = (await run(client))["recommendations"]["recent"][0]
    assert rec["status"] == "POSTED" and rec["allocation_id"] == 1 and len(fake_sim.posts) == 1


def test_idempotency_keys_do_not_depend_on_database_ids():
    from app.services.recommendation_service import idempotency_key, new_idempotency_key

    a, b = new_idempotency_key("station-x", "DIESEL", 5000), new_idempotency_key("station-x", "DIESEL", 5000)
    assert a != b  # a fresh database (ids from 1 again) can't collide with keys the simulator already holds

    class Rec:
        idempotency_key, station_id, fuel_type = a, "station-x", "DIESEL"

    assert idempotency_key(Rec, 5000) == a  # retry: same key
    assert idempotency_key(Rec, 3000) == a.removesuffix("-5000") + "-3000"  # new quantity: new key


def test_recheck_limits():
    sim = FakeSimulator()
    sim.station("station-mirpur")["inventory"]["DIESEL"] = 12000  # 3,000 L free
    w = sim.world
    world = World(instance=w["instance"], depots={d["id"]: d for d in w["depots"]},
                  stations={s["id"]: s for s in w["stations"]}, routes={r["id"]: r for r in w["routes"]},
                  supply=[], events=[], allocations=[], history=[], metrics={})
    args = dict(station_id="station-mirpur", fuel_type="DIESEL", depot_id="depot-gazipur",
                route_id="route-gazipur-mirpur", min_shipment=500, depot_reserve=0)
    assert recheck(world, quantity=7000, can_grow=True, **args).quantity == 3000
    assert recheck(world, quantity=1000, can_grow=True, **args).quantity == 3000  # auto plans grow to fit
    assert recheck(world, quantity=1000, can_grow=False, **args).quantity == 1000  # operator's number is a cap
    assert recheck(world, quantity=300, can_grow=False, **args).quantity == 300  # operator may go below the minimum

    sim.station("station-mirpur")["inventory"]["DIESEL"] = 14800
    full = recheck(world, quantity=7000, can_grow=True, **args)
    assert full.code == "DESTINATION_CAPACITY_EXCEEDED" and not full.retry
    sim.station("station-mirpur")["inventory"]["DIESEL"] = 1000
    world.allocations = [{"source_depot_id": "depot-gazipur", "destination_station_id": "station-tongi",
                          "fuel_type": "PETROL", "quantity": 12000, "status": "PENDING", "created_tick": 100}]
    busy = recheck(world, quantity=7000, can_grow=True, **args)
    assert busy.code == "DISPATCH_CAPACITY_EXCEEDED" and busy.retry


async def test_predict_failure_falls_back_to_last_rates(app, client, fake_sim, monkeypatch):
    await run(client)

    def boom(self, world):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(MovingAveragePredictor, "predict", boom)
    fake_sim.world["instance"]["tick"] = 101
    state = await run(client)
    assert stage_status(state)["predict"] == "fallback"
    assert all(f["source"] == "last_known_rate" and f["rate_per_tick"] == 100 for s in state["stations"] for f in s["fuels"])


async def test_reset_expires_open_recommendations(client, fake_sim, manual_approval):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300
    await run(client)
    fake_sim.world["instance"]["tick"] = 5
    state = await run(client)
    assert state["alerts"][0]["code"] == "SIMULATOR_RESET"
    statuses = [r["status"] for r in state["recommendations"]["recent"]]
    assert statuses.count("EXPIRED") == 1


async def test_health_reports_pipeline(client):
    body = (await client.get("/api/v1/health")).json()
    assert body["simulator"]["circuit"] == "closed" and body["pipeline"]["enabled"] is False


async def test_dashboard_stream_sends_state_first(client):
    stream = DashboardService(get_pipeline_state()).stream()
    first = await anext(stream)
    assert first.startswith("event: state\ndata: {")
    get_pipeline_state().publish("state", {"hello": 1})
    assert await anext(stream) == 'event: state\ndata: {"hello": 1}\n\n'
    await stream.aclose()
    assert get_pipeline_state().subscriber_count == 0


def test_planner_respects_dispatch_limit_and_urgency_order():
    sim = FakeSimulator()
    sim.station("station-mirpur")["inventory"]["DIESEL"] = 200  # most urgent
    sim.station("station-mirpur")["inventory"]["PETROL"] = 500
    sim.station("station-tongi")["inventory"]["DIESEL"] = 600
    w = sim.world
    world = World(instance=w["instance"], depots={d["id"]: d for d in w["depots"]},
                  stations={s["id"]: s for s in w["stations"]}, routes={r["id"]: r for r in w["routes"]},
                  supply=[], events=[], allocations=[], history=sim._history(500), metrics={})
    forecasts = MovingAveragePredictor(8, 8, 2).predict(world)
    plans, blocked = RulePlanner(500, 0).plan(world, forecasts, skip=set())
    # Gazipur can dispatch 12,000 per tick: 7,000 (Mirpur diesel) + 5,000 (Mirpur petrol, capped by
    # the dispatch limit). Tongi diesel has no other route, so it is blocked this tick.
    assert [(p.station_id, p.fuel_type, p.depot_id, p.quantity) for p in plans[:2]] == [
        ("station-mirpur", "DIESEL", "depot-gazipur", 7000), ("station-mirpur", "PETROL", "depot-gazipur", 5000)]
    assert [(b.station_id, b.fuel_type) for b in blocked] == [("station-tongi", "DIESEL")]


def test_circuit_breaker():
    breaker = CircuitBreaker(threshold=2, cooldown_seconds=0)
    breaker.failure()
    assert breaker.allow()
    breaker.failure()
    assert breaker.state == "half_open"  # cooldown 0 -> immediately half-open
    breaker.success()
    assert breaker.state == "closed"


async def test_expiry_needs_both_ticks_and_seconds(client, fake_sim, monkeypatch, manual_approval):
    from app.core.config import get_settings

    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 800  # 8 ticks of fuel: the card may wait
    await run(client)
    fake_sim.world["instance"]["tick"] = 100 + 49  # past APPROVAL_TTL_TICKS (48)...
    state = await run(client)
    assert state["recommendations"]["open"][0]["status"] == "PENDING_APPROVAL"  # ...but only milliseconds old

    monkeypatch.setattr(get_settings(), "APPROVAL_MIN_SECONDS", 0)
    fake_sim.world["instance"]["tick"] = 150
    state = await run(client)
    statuses = [r["status"] for r in state["recommendations"]["recent"]]
    assert statuses.count("EXPIRED") == 1 and statuses.count("PENDING_APPROVAL") == 1  # replaced by a fresh one


async def test_unanswered_urgent_card_auto_approves_at_its_deadline(client, fake_sim, monkeypatch, manual_approval):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300  # urgent + auto-post off -> operator card
    state = await run(client)
    assert state["recommendations"]["open"][0]["status"] == "PENDING_APPROVAL" and fake_sim.posts == []
    monkeypatch.setattr(get_settings(), "DEADLINE_TOLERANCE_TICKS", 0.0)  # no loss allowed
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 0  # nobody answered; the tank ran dry
    fake_sim.world["instance"]["tick"] = 101
    state = await run(client)
    rec = state["recommendations"]["recent"][0]
    assert rec["decision_mode"] == "auto-deadline" and rec["status"] == "POSTED"
    assert fake_sim.posts and fake_sim.posts[0]["destination_station_id"] == "station-mirpur"


async def test_deadline_never_lets_the_tank_run_dry(client, fake_sim, monkeypatch, manual_approval):
    monkeypatch.setattr(get_settings(), "DEADLINE_TOLERANCE_TICKS", 100.0)  # loss alone would allow a long wait
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300  # 3 ticks of fuel, truck needs 2 (+1 safety)
    await run(client)
    fake_sim.world["instance"]["tick"] = 101
    state = await run(client)
    rec = state["recommendations"]["recent"][0]
    assert rec["decision_mode"] == "auto-deadline" and rec["status"] == "POSTED"
    assert "run dry" in rec["operator_note"]


async def test_deadline_waits_while_the_tank_covers_wait_plus_transit(client, fake_sim, monkeypatch, manual_approval):
    monkeypatch.setattr(get_settings(), "DEADLINE_TOLERANCE_TICKS", 100.0)
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800  # 8 ticks of fuel, truck needs 2 (+1 safety)
    await run(client)
    fake_sim.world["instance"]["tick"] = 101
    state = await run(client)
    (rec,) = state["recommendations"]["open"]
    assert rec["status"] == "PENDING_APPROVAL" and fake_sim.posts == []
    deadline = rec["deadline"]
    assert deadline["limited_by"] == "never_dry" and 101 < deadline["tick"] <= 101 + 8 - 2 - 1
    assert deadline["must_keep_liters"] <= 800
