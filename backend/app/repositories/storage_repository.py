"""Supabase Storage access over its REST API (no SDK). Storage is a data source,
so it lives with the repositories. Inject it with the `Storage` dependency."""

from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import ExternalServiceError, NotFoundError, ServiceUnavailableError


class StorageRepository:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.SUPABASE_URL.rstrip("/")
        self.bucket = settings.SUPABASE_BUCKET_NAME
        self._key = settings.SUPABASE_SERVICE_ROLE_KEY
        self._http: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.bucket and self._key)

    @property
    def http(self) -> httpx.AsyncClient:
        if not self.is_configured:
            raise ServiceUnavailableError(
                "Storage is not configured: set SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and SUPABASE_BUCKET_NAME",
                code="STORAGE_NOT_CONFIGURED",
            )
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=f"{self.base_url}/storage/v1",
                headers={"Authorization": f"Bearer {self._key}", "apikey": self._key},
                timeout=30.0,
            )
        return self._http

    async def upload(self, path: str, content: bytes, content_type: str, *, upsert: bool = False) -> None:
        response = await self.http.post(
            f"/object/{self.bucket}/{path}",
            content=content,
            headers={"Content-Type": content_type, "x-upsert": str(upsert).lower()},
        )
        self._raise_for_status(response)

    async def list(self, prefix: str = "", *, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        response = await self.http.post(
            f"/object/list/{self.bucket}",
            json={"prefix": prefix, "limit": limit, "offset": offset,
                  "sortBy": {"column": "created_at", "order": "desc"}},
        )
        self._raise_for_status(response)
        return [obj for obj in response.json() if obj.get("id")]  # entries without id are folders

    async def create_signed_url(self, path: str, expires_in: int) -> str:
        response = await self.http.post(f"/object/sign/{self.bucket}/{path}", json={"expiresIn": expires_in})
        self._raise_for_status(response, path)
        return f"{self.base_url}/storage/v1{response.json()['signedURL']}"

    def public_url(self, path: str) -> str:
        """Only works if the bucket is public."""
        return f"{self.base_url}/storage/v1/object/public/{self.bucket}/{path}"

    async def delete(self, path: str) -> None:
        response = await self.http.request("DELETE", f"/object/{self.bucket}", json={"prefixes": [path]})
        self._raise_for_status(response)
        if not response.json():
            raise NotFoundError(f"File '{path}' not found")

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    @staticmethod
    def _raise_for_status(response: httpx.Response, path: str | None = None) -> None:
        if response.status_code < 400:
            return
        body = response.text[:300]
        if response.status_code == 404 or (response.status_code == 400 and "not_found" in body.lower()):
            raise NotFoundError(f"File '{path}' not found" if path else "Storage object not found")
        raise ExternalServiceError(
            "Supabase Storage request failed",
            code="STORAGE_ERROR",
            details={"status": response.status_code, "body": body},
        )


_storage: StorageRepository | None = None


def get_storage_repository() -> StorageRepository:
    global _storage
    if _storage is None:
        _storage = StorageRepository(get_settings())
    return _storage


async def close_storage_repository() -> None:
    global _storage
    if _storage is not None:
        await _storage.aclose()
        _storage = None
