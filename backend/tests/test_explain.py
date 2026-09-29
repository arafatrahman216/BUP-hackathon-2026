import json

import pytest

from app.ai import get_llm_client
from app.core.config import get_settings
from app.explainability import METRICS, MetricContext, Snapshot, Subject, build_context, load_profiles
from app.pipeline.types import World
from tests.conftest import FakeProvider, make_client

pytestmark = pytest.mark.anyio


class RecordingProvider(FakeProvider):
    """Remembers the messages it was sent."""

    async def generate(self, messages, **kwargs):
        self.messages = messages
        return await super().generate(messages, **kwargs)


def sent_context(provider: RecordingProvider) -> dict:
    return json.loads(provider.messages[-1].content.split("Context (JSON):\n", 1)[1])


@pytest.fixture
def gemini(app) -> RecordingProvider:
    provider = RecordingProvider("gemini", reply="  Mirpur petrol covers 2.7 ticks.  ")
    llm = make_client("gemini", [provider])
    app.dependency_overrides[get_llm_client] = lambda: llm
    return provider


async def urgent_recommendation(client, fake_sim) -> dict:
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 300  # cover 3 ticks -> urgent; pending with auto-post off
    await client.post("/api/v1/pipeline/run")
    return (await client.get("/api/v1/recommendations")).json()["items"][0]


# --- module (no HTTP) ---

def test_profiles_reference_registered_metrics():
    book = load_profiles()
    assert book.default_profile in book.profiles
    for profile in book.profiles.values():
        assert set(profile.metrics) <= set(METRICS), profile.name
    rec = book.profiles["recommendation"]
    assert rec.suggestions("PENDING_APPROVAL") and rec.suggestions("UNKNOWN") == rec.suggested_questions["default"]


def test_subject_is_filled_from_an_allocation_and_overrides_win():
    s = Subject.build({"destination_station_id": "st-1", "source_depot_id": "d-1", "fuel_type": "diesel"},
                      depot_id="d-2")
    assert s.ids() == {"station_id": "st-1", "fuel_type": "DIESEL", "depot_id": "d-2"}


def test_broken_metric_is_reported_not_raised():
    world = World(instance={"tick": 5}, depots={}, stations={"x": {"id": "x", "capacity": {"DIESEL": "n/a"}}},
                  routes={}, supply=[], events=[], allocations=[], history=[], metrics={}, stale=True)
    ctx = MetricContext(snapshot=Snapshot(world, {}, []), subject=Subject(station_id="x"))
    built = build_context(["clock", "station"], ctx, notes=["hello"])
    assert built.context["clock"]["tick"] == 5
    assert [e["metric"] for e in built.errors] == ["station"] and built.context["_unavailable"] == ["station"]
    assert built.context["_meta"]["stale_data"] is True and built.context["_meta"]["notes"] == ["hello"]


# --- HTTP API ---

async def test_catalog_lists_profiles_and_metrics(client):
    body = (await client.get("/api/v1/explain/profiles")).json()
    assert "PENDING_APPROVAL" in body["profiles"]["recommendation"]["suggested_questions"]
    assert {m["name"] for m in body["metrics"]} == set(METRICS)


async def test_without_pipeline_cache_it_reads_live_with_the_same_rules(client, fake_sim):
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800
    body = (await client.post("/api/v1/explain/context", json={
        "profile": "station", "station_id": "station-tongi", "fuel_type": "diesel"})).json()
    assert body["data_source"] == "live" and body["tick"] == 100
    f = body["context"]["forecast"]["DIESEL"]
    assert (f["risk"], f["cover_ticks"], f["lead_ticks"], f["margin_ticks"]) == ("watch", 8.0, 2, 6.0)
    assert body["context"]["risk_rules"]["this_station"]["DIESEL"] == {
        "cover_ticks": 8.0, "urgent_below_cover": 4, "watch_below_cover": 10, "risk": "watch", "gets_shipment": True}
    assert "has not run yet" in body["context"]["_meta"]["notes"][0]


async def test_uses_the_pipeline_cache_forecasts_and_alerts(client, fake_sim, manual_approval):
    rec = await urgent_recommendation(client, fake_sim)
    fake_sim.station("station-mirpur")["inventory"]["PETROL"] = 14000  # changes after the run are not seen
    body = (await client.post("/api/v1/explain/context", json={"profile": "recommendation",
                                                               "recommendation_id": rec["id"]})).json()
    ctx = body["context"]
    assert body["data_source"] == "pipeline_cache"
    assert ctx["forecast"]["PETROL"]["risk"] == "urgent" and ctx["forecast"]["PETROL"]["inventory_l"] == 300
    assert any(a["code"] == "STOCKOUT_RISK" for a in ctx["alerts"])
    assert ctx["action"]["status"] == "PENDING_APPROVAL" and ctx["action"]["ticks_since_proposed"] == 0
    assert "idempotency_key" not in ctx["action"]
    mirpur = next(s for s in ctx["depot_stations"]["PETROL"]["stations"] if s["is_subject"])
    assert mirpur["station_id"] == "station-mirpur"
    assert ctx["depot_commitments"]["stock_after_open_l"]["PETROL"] == 45000 - rec["quantity"]


async def test_trend_based_run_out(client, fake_sim):
    real = fake_sim._history

    def rising(limit):  # Tongi diesel +6 L every tick
        return [{**r, "demand_liters": 60 + 6 * (r["tick"] - 81)} if (r["station_id"], r["fuel_type"]) ==
                ("station-tongi", "DIESEL") else r for r in real(limit)]
    fake_sim._history = rising
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 2200
    body = (await client.post("/api/v1/explain/context", json={
        "metrics": ["demand"], "station_id": "station-tongi", "fuel_type": "DIESEL"})).json()
    d = body["context"]["demand"]["DIESEL"]
    assert d["latest_l"] == 168 and d["slope_l_per_tick"] == 6.0
    assert 10 < d["cover_ticks_if_trend_continues"] < 12


async def test_general_profile_ranks_stations(client, fake_sim):
    fake_sim.station("station-tongi")["inventory"]["PETROL"] = 500
    body = (await client.post("/api/v1/explain/context", json={"profile": "general"})).json()
    first = body["context"]["station_ranking"][0]
    assert (first["station_id"], first["fuel_type"], first["cover_ticks"]) == ("station-tongi", "PETROL", 5.0)


async def test_ask_about_a_recommendation_is_stored(client, fake_sim, gemini, manual_approval):
    rec = await urgent_recommendation(client, fake_sim)
    history = (await client.get(f"/api/v1/explain/recommendations/{rec['id']}")).json()
    assert history["status"] == "PENDING_APPROVAL" and history["items"] == []
    assert "Why does this need my approval?" in history["suggestions"]

    asked = await client.post(f"/api/v1/explain/recommendations/{rec['id']}",
                              json={"question": "Can I send less, and how long would it last?"})
    body = asked.json()
    assert asked.status_code == 200, body
    assert body["answer"] == "Mirpur petrol covers 2.7 ticks." and body["provider"] == "gemini"
    assert body["tick"] == 100 and body["profile"] == "recommendation"
    assert body["context"] == sent_context(gemini)
    assert "Can I send less" in gemini.messages[-1].content
    assert "Task:" in gemini.messages[0].content and "risk_rules" in gemini.messages[0].content

    history = (await client.get(f"/api/v1/explain/recommendations/{rec['id']}")).json()
    assert [q["question"] for q in history["items"]] == ["Can I send less, and how long would it last?"]


async def test_why_approval_on_a_pending_card_is_the_scenario_template(client, fake_sim, gemini, manual_approval):
    fake_sim.world["depots"][0]["inventory"]["PETROL"] = 8000
    rec = await urgent_recommendation(client, fake_sim)
    body = (await client.post(f"/api/v1/explain/recommendations/{rec['id']}",
                              json={"question": "Why does this need my approval?"})).json()
    assert body["provider"] == "template" and not hasattr(gemini, "messages")  # no LLM call
    answer = body["answer"]
    assert answer.startswith('**"One depot, two stations running dry"**')
    assert "* Gazipur Depot has 8,000 L of petrol left" in answer
    assert "the optimizer plans 7,000 L for it. That's 88% of the depot's stock" in answer
    assert '* Tongi also runs on Gazipur Depot petrol and is on "watch"' in answer and "only 1,000 L left" in answer
    assert "* edit it down to about 4,000 L so both stations get something" in answer
    assert body["context"]["action"]["id"] == rec["id"]


async def test_old_action_is_flagged(client, fake_sim, manual_approval):
    rec = await urgent_recommendation(client, fake_sim)
    fake_sim.world["instance"]["tick"] = 130
    await client.post("/api/v1/pipeline/run")
    ctx = (await client.post("/api/v1/explain/context", json={"recommendation_id": rec["id"],
                                                              "metrics": ["action"]})).json()["context"]
    assert ctx["action"]["ticks_since_proposed"] == 30
    assert any("proposed at tick 100" in n for n in ctx["_meta"]["notes"])


async def test_inline_action_and_metric_override(client, gemini):
    response = await client.post("/api/v1/explain", json={
        "question": "What is this?", "metrics": ["action", "clock"],
        "action": {"kind": "what-if", "station_id": "station-mirpur", "quantity": 1234},
    })
    assert response.status_code == 200, response.text
    assert set(sent_context(gemini)) == {"_meta", "action", "clock"}


async def test_explain_an_allocation(client, fake_sim):
    fake_sim.world["allocations"].append({"id": 7, "destination_station_id": "station-tongi", "fuel_type": "DIESEL",
                                          "source_depot_id": "depot-gazipur", "quantity": 900, "status": "FAILED",
                                          "failure_reason": "ROUTE_DISRUPTED", "created_tick": 99})
    body = (await client.post("/api/v1/explain/context", json={"profile": "station", "allocation_id": 7})).json()
    assert body["context"]["_meta"]["subject"]["station_id"] == "station-tongi"
    assert body["context"]["recent_allocations"][0]["failure_reason"] == "ROUTE_DISRUPTED"


async def test_events_filter_by_subject_but_general_questions_see_all(client, fake_sim):
    fake_sim.world["events"] = [{"id": 1, "type": "FLOOD", "status": "ACTIVE", "parameters": {"region_ids": ["region-dhaka"]}},
                                {"id": 2, "type": "STRIKE", "status": "ACTIVE", "parameters": {"depot_ids": ["depot-patiya"]}}]
    general = (await client.post("/api/v1/explain/context", json={"metrics": ["events"]})).json()
    assert [e["id"] for e in general["context"]["events"]] == [1, 2]
    scoped = (await client.post("/api/v1/explain/context", json={
        "metrics": ["events"], "station_id": "station-mirpur", "depot_id": "depot-gazipur"})).json()
    assert [e["id"] for e in scoped["context"]["events"]] == [1]


async def test_errors(client, fake_sim):
    bad_profile = await client.post("/api/v1/explain/context", json={"profile": "nope"})
    assert bad_profile.status_code == 400 and bad_profile.json()["error"]["code"] == "UNKNOWN_PROFILE"
    bad_metric = await client.post("/api/v1/explain/context", json={"metrics": ["clock", "nope"]})
    assert bad_metric.status_code == 400 and bad_metric.json()["error"]["code"] == "UNKNOWN_METRIC"
    assert (await client.get("/api/v1/explain/recommendations/999")).status_code == 404
    fake_sim.down = True  # no cache and no simulator
    down = await client.post("/api/v1/explain", json={"question": "hi"})
    assert down.status_code == 503 and down.json()["error"]["code"] == "SIMULATOR_UNAVAILABLE"


async def test_simulator_down_after_a_run_explains_from_cache(client, fake_sim, gemini, manual_approval):
    rec = await urgent_recommendation(client, fake_sim)
    fake_sim.down = True
    response = await client.post(f"/api/v1/explain/recommendations/{rec['id']}", json={"question": "Why?"})
    assert response.status_code == 200, response.text
    notes = response.json()["context"]["_meta"]["notes"]
    assert any("longer demand history unavailable" in n for n in notes)


async def test_posted_action_explains_its_truck_and_the_models_forecast(client, fake_sim):
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 800  # watch -> auto-posted
    await client.post("/api/v1/pipeline/run")
    rec = next(r for r in (await client.get("/api/v1/recommendations")).json()["items"] if r["status"] == "POSTED")
    ctx = (await client.post("/api/v1/explain/context", json={"profile": "recommendation",
                                                               "recommendation_id": rec["id"]})).json()["context"]
    assert ctx["allocation"]["id"] == rec["allocation_id"] and ctx["allocation"]["status"] == "PENDING"
    assert ctx["risk_rules"]["predictor"] == get_settings().PREDICTOR
    assert "p_stockout" in ctx["forecast"]["DIESEL"] and "demand_next_ticks_l" in ctx["forecast"]["DIESEL"]
