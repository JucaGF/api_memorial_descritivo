from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GeneratedMemorialResponse(BaseModel):
    id: str
    type: str
    project_name: str
    status: str
    observations: str | None = None
    pdf_filenames: list[str]
    created_at: datetime
    updated_at: datetime
    download_url: str


class GeneratedMemorialListResponse(BaseModel):
    memorials: list[GeneratedMemorialResponse]


class GeneratedMemorialDownloadResponse(BaseModel):
    download_url: str
