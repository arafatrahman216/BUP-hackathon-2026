import pytest

pytestmark = pytest.mark.anyio


async def test_status_reports_components_and_traffic(client):
    await client.get("/api/v1/health")
    res = await client.get("/api/v1/status")
    assert res.status_code == 200
    body = res.json()
    assert set(body["components"]) == {"backend_api", "database", "simulator", "prediction", "decision"}
    assert body["components"]["database"]["status"] == "healthy"
    assert body["components"]["simulator"]["status"] == "down"  # no pipeline run in tests
    assert body["status"] == "down"
    assert body["requests"] >= 1 and body["p95_latency_ms"] is not None
    assert 0 <= body["error_rate"] <= 1


async def test_metrics_exposes_prometheus_text(client):
    await client.get("/api/v1/health")
    res = await client.get("/api/v1/metrics")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    text = res.text
    assert 'component_health{component="database"} 1.0' in text
    assert 'http_requests_total{method="GET",route="/health",status="200"}' in text
    assert "http_request_duration_seconds_bucket" in text
