from __future__ import annotations

from pydantic import BaseModel


class UploadedFileResponse(BaseModel):
    filename: str
    content_type: str
    extension: str
    size_bytes: int


class FileIngestionResponse(BaseModel):
    files: list[UploadedFileResponse]
