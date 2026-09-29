import re
import uuid

from fastapi import UploadFile

from app.core.exceptions import BadRequestError
from app.repositories.storage_repository import StorageRepository
from app.schemas.file import SignedUrl, StoredFile, UploadedFile

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _clean_segment(segment: str) -> str:
    return _UNSAFE.sub("-", segment).strip("-.")


def clean_folder(folder: str) -> str:
    parts = folder.split("/")
    if ".." in parts:
        raise BadRequestError("Invalid folder name")
    return "/".join(filter(None, (_clean_segment(p) for p in parts)))


def clean_path(path: str) -> str:
    path = path.strip("/")
    if not path or ".." in path.split("/"):
        raise BadRequestError("Invalid file path")
    return path


class FileService:
    def __init__(self, storage: StorageRepository, max_upload_mb: int) -> None:
        self.storage = storage
        self.max_bytes = max_upload_mb * 1024 * 1024

    async def upload(self, file: UploadFile, folder: str = "uploads") -> UploadedFile:
        content = await file.read(self.max_bytes + 1)
        if len(content) > self.max_bytes:
            raise BadRequestError(f"File is larger than {self.max_bytes // (1024 * 1024)} MB", code="FILE_TOO_LARGE")
        if not content:
            raise BadRequestError("File is empty", code="FILE_EMPTY")

        name = _clean_segment(file.filename or "file") or "file"
        prefix = clean_folder(folder)
        path = f"{prefix}/{uuid.uuid4().hex[:8]}-{name}" if prefix else f"{uuid.uuid4().hex[:8]}-{name}"
        content_type = file.content_type or "application/octet-stream"

        await self.storage.upload(path, content, content_type)
        return UploadedFile(
            name=path.rsplit("/", 1)[-1],
            path=path,
            size=len(content),
            content_type=content_type,
            public_url=self.storage.public_url(path),
            signed_url=await self.storage.create_signed_url(path, 3600),
        )

    async def list(self, prefix: str = "uploads") -> list[StoredFile]:
        prefix = clean_folder(prefix)
        objects = await self.storage.list(prefix)
        files = []
        for obj in objects:
            path = f"{prefix}/{obj['name']}" if prefix else obj["name"]
            meta = obj.get("metadata") or {}
            files.append(StoredFile(
                name=obj["name"],
                path=path,
                size=meta.get("size"),
                content_type=meta.get("mimetype"),
                created_at=obj.get("created_at"),
                public_url=self.storage.public_url(path),
            ))
        return files

    async def signed_url(self, path: str, expires_in: int) -> SignedUrl:
        path = clean_path(path)
        return SignedUrl(path=path, signed_url=await self.storage.create_signed_url(path, expires_in), expires_in=expires_in)

    async def delete(self, path: str) -> None:
        await self.storage.delete(clean_path(path))
