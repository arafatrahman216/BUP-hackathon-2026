import json

import httpx
import pytest

from app.core.config import Settings
from app.core.dependencies import get_storage_repository
from app.repositories.storage_repository import StorageRepository

pytestmark = pytest.mark.anyio

API = "/api/v1/files"


def fake_supabase(request: httpx.Request) -> httpx.Response:
    """Minimal stand-in for the Supabase Storage REST API."""
    path = request.url.path.removeprefix("/storage/v1")
    if request.method == "POST" and path.startswith("/object/sign/bucket/"):
        if "missing" in path:
            return httpx.Response(400, json={"error": "not_found", "message": "Object not found"})
        return httpx.Response(200, json={"signedURL": f"/object/sign/bucket/{path.split('/bucket/')[1]}?token=t"})
    if request.method == "POST" and path == "/object/list/bucket":
        assert json.loads(request.content)["prefix"] == "uploads"
        return httpx.Response(200, json=[
            {"name": "sub", "id": None},
            {"name": "a.png", "id": "1", "created_at": "2026-09-29T00:00:00Z",
             "metadata": {"size": 3, "mimetype": "image/png"}},
        ])
    if request.method == "POST" and path.startswith("/object/bucket/"):
        assert request.headers["authorization"] == "Bearer service-key"
        return httpx.Response(200, json={"Key": path})
    if request.method == "DELETE":
        prefixes = json.loads(request.content)["prefixes"]
        return httpx.Response(200, json=[] if "missing" in prefixes[0] else [{"name": prefixes[0]}])
    return httpx.Response(500)


@pytest.fixture
def storage(app):
    repo = StorageRepository(Settings(
        SUPABASE_URL="https://ref.supabase.co", SUPABASE_SERVICE_ROLE_KEY="service-key", SUPABASE_BUCKET_NAME="bucket",
    ))
    repo._http = httpx.AsyncClient(
        base_url="https://ref.supabase.co/storage/v1",
        headers={"Authorization": "Bearer service-key"},
        transport=httpx.MockTransport(fake_supabase),
    )
    app.dependency_overrides[get_storage_repository] = lambda: repo
    return repo


async def test_upload_list_sign_delete(client, storage):
    uploaded = await client.post(API, files={"file": ("my photo!.png", b"abc", "image/png")})
    assert uploaded.status_code == 201, uploaded.text
    body = uploaded.json()
    assert body["path"].startswith("uploads/") and body["path"].endswith("-my-photo-.png")
    assert body["signed_url"].startswith("https://ref.supabase.co/storage/v1/object/sign/bucket/uploads/")
    assert body["public_url"] == f"https://ref.supabase.co/storage/v1/object/public/bucket/{body['path']}"

    files = (await client.get(API)).json()
    assert [f["path"] for f in files] == ["uploads/a.png"] and files[0]["size"] == 3

    signed = (await client.get(f"{API}/signed-url", params={"path": "uploads/a.png"})).json()
    assert signed["expires_in"] == 3600

    assert (await client.delete(API, params={"path": "uploads/a.png"})).status_code == 204


async def test_missing_file_is_404(client, storage):
    assert (await client.delete(API, params={"path": "uploads/missing"})).json()["error"]["code"] == "NOT_FOUND"
    assert (await client.get(f"{API}/signed-url", params={"path": "missing"})).status_code == 404


async def test_path_traversal_rejected(client, storage):
    response = await client.post(API, files={"file": ("a.txt", b"x")}, data={"folder": "../secret"})
    assert response.json()["error"]["code"] == "BAD_REQUEST"


async def test_storage_not_configured(app, client):
    app.dependency_overrides[get_storage_repository] = lambda: StorageRepository(Settings(
        SUPABASE_URL="", SUPABASE_SERVICE_ROLE_KEY="", SUPABASE_BUCKET_NAME="",
    ))
    response = await client.get(API)
    assert response.status_code == 503 and response.json()["error"]["code"] == "STORAGE_NOT_CONFIGURED"


def test_database_url_from_supabase():
    base = dict(DATABASE_URL="", SUPABASE_URL="https://abc123.supabase.co", SUPABASE_PASSWORD="p@ss/word")
    direct = Settings(**base, SUPABASE_POOLER_HOST="").database_url
    assert direct == "postgresql+asyncpg://postgres:p%40ss%2Fword@db.abc123.supabase.co:5432/postgres"
    pooled = Settings(**base, SUPABASE_POOLER_HOST="aws-0-x.pooler.supabase.com").database_url
    assert pooled.startswith("postgresql+asyncpg://postgres.abc123:p%40ss%2Fword@aws-0-x.pooler.supabase.com:5432/")
    assert Settings(DATABASE_URL="sqlite+aiosqlite:///x.db").database_url == "sqlite+aiosqlite:///x.db"
    with pytest.raises(ValueError):
        Settings(DATABASE_URL="", SUPABASE_URL="", SUPABASE_PASSWORD="").database_url
