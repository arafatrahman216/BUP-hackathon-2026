from datetime import datetime

from pydantic import BaseModel


class StoredFile(BaseModel):
    name: str
    path: str
    size: int | None = None
    content_type: str | None = None
    created_at: datetime | None = None
    public_url: str | None = None


class UploadedFile(StoredFile):
    signed_url: str


class SignedUrl(BaseModel):
    path: str
    signed_url: str
    expires_in: int
