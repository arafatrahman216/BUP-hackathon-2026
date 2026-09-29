from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.core.dependencies import get_file_service
from app.schemas.file import SignedUrl, StoredFile, UploadedFile
from app.services.file_service import FileService

router = APIRouter(prefix="/files", tags=["files"])

Service = Annotated[FileService, Depends(get_file_service)]


@router.get("", response_model=list[StoredFile])
async def list_files(service: Service, prefix: str = "uploads"):
    return await service.list(prefix)


@router.post("", response_model=UploadedFile, status_code=status.HTTP_201_CREATED)
async def upload_file(service: Service, file: UploadFile = File(...), folder: str = Form("uploads")):
    return await service.upload(file, folder)


@router.get("/signed-url", response_model=SignedUrl)
async def signed_url(service: Service, path: str, expires_in: int = Query(3600, ge=60, le=7 * 24 * 3600)):
    return await service.signed_url(path, expires_in)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(service: Service, path: str) -> None:
    await service.delete(path)
