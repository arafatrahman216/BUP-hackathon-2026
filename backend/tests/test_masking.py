"""DEMO_MASK_ERRORS: the dashboard never shows an error; the log says "ERROR MASKED"."""

import logging

import pytest

from app import pipeline
from app.core.config import get_settings
from app.pipeline.state import get_pipeline_state

pytestmark = pytest.mark.anyio


@pytest.fixture
def masking(monkeypatch):
    monkeypatch.setattr(get_settings(), "DEMO_MASK_ERRORS", True)


def boom(*args, **kwargs):
    raise RuntimeError("model exploded")


async def run(client) -> dict:
    assert (await client.post("/api/v1/pipeline/run")).status_code == 200
    response = await client.get("/api/v1/dashboard")
    assert response.status_code == 200
    return response.json()


def statuses(state: dict) -> set[str]:
    return {s["status"] for s in state["pipeline"]["stages"]}


async def test_simulator_never_reached_shows_baseline_world(client, fake_sim, masking, caplog):
    fake_sim.down = True
    with caplog.at_level(logging.ERROR):
        state = await run(client)
    assert "error" not in statuses(state)
    assert state["sim"]["demo"] is True and len(state["stations"]) == 4 and len(state["routes"]) == 6
    assert all(f["rate_per_tick"] for s in state["stations"] for f in s["fuels"])
    assert "ConnectError" not in str(state) and "FAULT_INJECTED" not in str(state)
    assert "ERROR MASKED" in caplog.text
    assert fake_sim.posts == []  # never act on backup data


async def test_predict_and_its_fallback_fail(client, fake_sim, masking, monkeypatch, caplog):
    class Broken:
        name = "broken"
        predict = staticmethod(boom)

    monkeypatch.setattr(pipeline, "build_predictor", lambda settings, state=None: Broken())
    monkeypatch.setattr("app.services.pipeline_service.LastKnownRatePredictor.predict", boom)
    with caplog.at_level(logging.ERROR):
        state = await run(client)
    assert "error" not in statuses(state)
    assert all(f["source"] == "backup" and f["rate_per_tick"] for s in state["stations"] for f in s["fuels"])
    assert caplog.text.count("ERROR MASKED") >= 2


async def test_planner_and_fallback_fail(client, fake_sim, masking, monkeypatch, caplog):
    fake_sim.station("station-tongi")["inventory"]["DIESEL"] = 300
    monkeypatch.setattr("app.pipeline.decide.RulePlanner.plan", boom)
    with caplog.at_level(logging.ERROR):
        state = await run(client)
    assert "error" not in statuses(state) and fake_sim.posts == []
    assert "ERROR MASKED in fallback planner" in caplog.text


async def test_dashboard_payload_failure_returns_last_good(client, fake_sim, masking, monkeypatch, caplog):
    good = await run(client)
    monkeypatch.setattr(type(get_pipeline_state()), "_build_dashboard", boom)
    with caplog.at_level(logging.ERROR):
        again = (await client.get("/api/v1/dashboard")).json()
    assert again["sim"]["tick"] == good["sim"]["tick"]
    assert "ERROR MASKED in dashboard payload" in caplog.text
