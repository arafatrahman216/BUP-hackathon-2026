import pytest
from app.core.config import get_settings

from app.pipeline.decide import RulePlanner
from app.pipeline.predict import MovingAveragePredictor
from app.pipeline.state import get_pipeline_state
from app.pipeline.types import World
from app.repositories.simulator_repository import CircuitBreaker
from app.services.dashboard_service import DashboardService
from tests.fake_simulator import FakeSimulator

pytestmark = pytest.mark.anyio

# Defaults: rate 100 L/tick, lead 2 ticks, SAFETY_TICKS 8, URGENT_MARGIN 2
#   cover < 4 -> urgent (operator), cover < 10 -> watch (auto), else safe.


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
    assert fake_sim.posts == [{
        "idempotency_key": "bup-rec-1-station-tongi-diesel-6500", "source_depot_id": "depot-gazipur",
        "destination_station_id": "station-tongi", "route_id": "route-gazipur-tongi", "fuel_type": "DIESEL",
        "quantity": 6500.0,
    }]
    rec = state["recommendations"]["recent"][0]
    assert rec["status"] == "POSTED" and rec["decision_mode"] == "auto" and rec["allocation_id"] == 1
    assert "Tongi DIESEL holds 800" in rec["explanation"]

    # next tick: the shipment is incoming, so nothing new is planned
    fake_sim.world["instance"]["tick"] = 101
    await run(client)
    assert len(fake_sim.posts) == 1


async def test_urgent_needs_operator_then_edit_and_approve(client, fake_sim):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300  # cover 3 ticks -> urgent
    state = await run(client)
    assert fake_sim.posts == []
    (rec,) = state["recommendations"]["open"]
    assert rec["status"] == "PENDING_APPROVAL" and rec["important"] and rec["risk"] == "urgent"
    assert any("urgent" in r for r in rec["reasons"])

    too_big = await client.post(f"/api/v1/recommendations/{rec['id']}/approve", json={"quantity": 9000})
    assert too_big.status_code == 400 and too_big.json()["error"]["code"] == "QUANTITY_TOO_LARGE"

    approved = (await client.post(f"/api/v1/recommendations/{rec['id']}/approve",
                                  json={"quantity": 5000, "note": "keep some room"})).json()
    assert approved["status"] == "POSTED" and approved["quantity"] == 5000 and approved["proposed_quantity"] == 7000
    assert fake_sim.posts[0]["quantity"] == 5000 and fake_sim.posts[0]["idempotency_key"].endswith("-5000")

    again = await client.post(f"/api/v1/recommendations/{rec['id']}/approve", json={})
    assert again.status_code == 409 and again.json()["error"]["code"] == "NOT_PENDING_APPROVAL"


async def test_reject(client, fake_sim):
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
    fake_sim.refuse = "DISPATCH_CAPACITY_EXCEEDED"
    rec = (await run(client))["recommendations"]["recent"][0]
    assert rec["status"] == "REFUSED" and rec["error_code"] == "DISPATCH_CAPACITY_EXCEEDED"


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


async def test_stale_data_is_not_acted_on(client, fake_sim):
    fake_sim.stale = True
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800
    state = await run(client)
    assert state["pipeline"]["acting"] is False
    assert stage_status(state)["validate"] == "fallback" and stage_status(state)["decide"] == "skipped"
    assert fake_sim.posts == []


async def test_predict_failure_falls_back_to_last_rates(app, client, fake_sim, monkeypatch):
    await run(client)

    def boom(self, world):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(MovingAveragePredictor, "predict", boom)
    fake_sim.world["instance"]["tick"] = 101
    state = await run(client)
    assert stage_status(state)["predict"] == "fallback"
    assert all(f["source"] == "last_known_rate" and f["rate_per_tick"] == 100 for s in state["stations"] for f in s["fuels"])


async def test_reset_expires_open_recommendations(client, fake_sim):
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


async def test_expiry_needs_both_ticks_and_seconds(client, fake_sim, monkeypatch):
    from app.core.config import get_settings

    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300
    await run(client)
    fake_sim.world["instance"]["tick"] = 100 + 49  # past APPROVAL_TTL_TICKS (48)...
    state = await run(client)
    assert state["recommendations"]["open"][0]["status"] == "PENDING_APPROVAL"  # ...but only milliseconds old

    monkeypatch.setattr(get_settings(), "APPROVAL_MIN_SECONDS", 0)
    fake_sim.world["instance"]["tick"] = 150
    state = await run(client)
    statuses = [r["status"] for r in state["recommendations"]["recent"]]
    assert statuses.count("EXPIRED") == 1 and statuses.count("PENDING_APPROVAL") == 1  # replaced by a fresh one


async def test_unanswered_urgent_card_auto_approves_at_its_deadline(client, fake_sim, monkeypatch):
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300  # urgent -> operator card
    state = await run(client)
    assert state["recommendations"]["open"][0]["status"] == "PENDING_APPROVAL" and fake_sim.posts == []
    monkeypatch.setattr(get_settings(), "DEADLINE_TOLERANCE_TICKS", 0.0)  # no loss allowed
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 0  # nobody answered; the tank ran dry
    fake_sim.world["instance"]["tick"] = 101
    state = await run(client)
    rec = state["recommendations"]["recent"][0]
    assert rec["decision_mode"] == "auto-deadline" and rec["status"] == "POSTED"
    assert fake_sim.posts and fake_sim.posts[0]["destination_station_id"] == "station-mirpur"
