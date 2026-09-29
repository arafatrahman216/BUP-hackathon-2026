import pytest

pytestmark = pytest.mark.anyio

API = "/api/v1/items"


def assert_error(response, status: int, code: str):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
    return body["error"]


async def test_crud_flow(client):
    created = await client.post(API, json={"name": "Widget", "price": 9.5})
    assert created.status_code == 201
    item = created.json()
    assert item["name"] == "Widget" and item["is_active"] is True

    fetched = await client.get(f"{API}/{item['id']}")
    assert fetched.json()["price"] == 9.5

    updated = await client.patch(f"{API}/{item['id']}", json={"description": "New"})
    assert updated.json()["description"] == "New"
    assert updated.json()["name"] == "Widget"

    deleted = await client.delete(f"{API}/{item['id']}")
    assert deleted.status_code == 204
    assert_error(await client.get(f"{API}/{item['id']}"), 404, "NOT_FOUND")


async def test_list_paginates_and_filters(client):
    for i in range(5):
        await client.post(API, json={"name": f"thing-{i}", "is_active": i % 2 == 0})

    page = (await client.get(API, params={"page": 2, "page_size": 2})).json()
    assert page["total"] == 5 and page["pages"] == 3 and len(page["items"]) == 2
    assert page["items"][0]["name"] == "thing-2"

    active = (await client.get(API, params={"is_active": True})).json()
    assert active["total"] == 3
    search = (await client.get(API, params={"search": "THING-4"})).json()
    assert [i["name"] for i in search["items"]] == ["thing-4"]


async def test_duplicate_name_conflict(client):
    await client.post(API, json={"name": "Dup"})
    assert_error(await client.post(API, json={"name": "Dup"}), 409, "CONFLICT")


async def test_validation_error_shape(client):
    error = assert_error(await client.post(API, json={"name": "", "price": -1}), 422, "VALIDATION_ERROR")
    fields = {d["field"] for d in error["details"]}
    assert {"body.name", "body.price"} <= fields


async def test_patch_rejects_null_for_required_field(client):
    item = (await client.post(API, json={"name": "X"})).json()
    assert_error(await client.patch(f"{API}/{item['id']}", json={"name": None}), 422, "VALIDATION_ERROR")


async def test_unknown_route_uses_error_shape(client):
    assert_error(await client.get("/api/v1/nope"), 404, "NOT_FOUND")


async def test_generate_description_uses_ai(client):
    item = (await client.post(API, json={"name": "Lamp", "price": 20})).json()
    response = await client.post(f"{API}/{item['id']}/generate-description")
    assert response.json()["description"] == "A shiny description."


async def test_health(client):
    body = (await client.get("/api/v1/health")).json()
    assert body["status"] == "ok" and body["database"] == "ok"


async def test_unhandled_error_is_500_with_cors(client, monkeypatch):
    from app.services.item_service import ItemService

    async def explode(self, item_id):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(ItemService, "get", explode)
    response = await client.get(f"{API}/1", headers={"Origin": "http://localhost:3000"})
    error = assert_error(response, 500, "INTERNAL_ERROR")
    assert "kaboom" not in str(error)  # hidden unless DEBUG=true
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
