import json

import httpx
import pytest

from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.repositories.storage_repository import StorageRepository

pytestmark = pytest.mark.anyio


def assert_error(response, status: int, code: str):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
    return body["error"]


async def test_health(client):
    body = (await client.get("/api/v1/health")).json()
    assert body["status"] == "ok" and body["database"] == "ok"


async def test_unknown_route_uses_error_shape(client):
    assert_error(await client.get("/api/v1/nope"), 404, "NOT_FOUND")


async def test_validation_error_shape(client):
    error = assert_error(await client.post("/api/v1/ai/generate", json={"prompt": ""}), 422, "VALIDATION_ERROR")
    assert error["details"][0]["field"] == "body.prompt"


async def test_app_exception_and_unhandled_error(app, client):
    @app.get("/boom/app")
    async def app_error():
        raise NotFoundError("Thing 1 not found")

    @app.get("/boom/crash")
    async def crash():
        raise RuntimeError("kaboom")

    assert assert_error(await client.get("/boom/app"), 404, "NOT_FOUND")["message"] == "Thing 1 not found"

    response = await client.get("/boom/crash", headers={"Origin": "http://localhost:3000"})
    error = assert_error(response, 500, "INTERNAL_ERROR")
    assert "kaboom" not in str(error)  # hidden unless DEBUG=true
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_database_url_from_supabase():
    base = dict(DATABASE_URL="", SUPABASE_URL="https://abc123.supabase.co", SUPABASE_PASSWORD="p@ss/word")
    direct = Settings(**base, SUPABASE_POOLER_HOST="").database_url
    assert direct == "postgresql+asyncpg://postgres:p%40ss%2Fword@db.abc123.supabase.co:5432/postgres"
    pooled = Settings(**base, SUPABASE_POOLER_HOST="aws-0-x.pooler.supabase.com").database_url
    assert pooled.startswith("postgresql+asyncpg://postgres.abc123:p%40ss%2Fword@aws-0-x.pooler.supabase.com:5432/")
    assert Settings(DATABASE_URL="sqlite+aiosqlite:///x.db").database_url == "sqlite+aiosqlite:///x.db"
    with pytest.raises(ValueError):
        Settings(DATABASE_URL="", SUPABASE_URL="", SUPABASE_PASSWORD="").database_url


def _storage(handler) -> StorageRepository:
    repo = StorageRepository(Settings(
        SUPABASE_URL="https://ref.supabase.co", SUPABASE_SERVICE_ROLE_KEY="key", SUPABASE_BUCKET_NAME="bucket",
    ))
    repo._http = httpx.AsyncClient(base_url="https://ref.supabase.co/storage/v1", transport=httpx.MockTransport(handler))
    return repo


async def test_storage_repository():
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/storage/v1/object/bucket/a/b.txt":
            return httpx.Response(200, json={})
        if path.startswith("/storage/v1/object/sign/"):
            return httpx.Response(200, json={"signedURL": "/object/sign/bucket/a/b.txt?token=t"})
        if request.method == "DELETE":
            return httpx.Response(200, json=[] if "missing" in json.loads(request.content)["prefixes"][0] else [{}])
        return httpx.Response(500)

    repo = _storage(handler)
    await repo.upload("a/b.txt", b"hi", "text/plain")
    assert await repo.create_signed_url("a/b.txt", 60) == "https://ref.supabase.co/storage/v1/object/sign/bucket/a/b.txt?token=t"
    assert repo.public_url("a/b.txt") == "https://ref.supabase.co/storage/v1/object/public/bucket/a/b.txt"
    await repo.delete("a/b.txt")
    with pytest.raises(NotFoundError):
        await repo.delete("missing")


def test_storage_not_configured():
    from app.core.exceptions import ServiceUnavailableError

    repo = StorageRepository(Settings(SUPABASE_URL="", SUPABASE_SERVICE_ROLE_KEY="", SUPABASE_BUCKET_NAME=""))
    with pytest.raises(ServiceUnavailableError):
        repo.http
