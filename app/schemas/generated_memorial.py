from __future__ import annotations

from datetime import datetime
from typing import Any

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
    context_version: str | None = None
    template_version: str | None = None
    final_context: dict[str, Any] | None = None
    extraction_report: dict[str, Any] | None = None
    conflicts: list[dict[str, Any]] | None = None


class GeneratedMemorialListResponse(BaseModel):
    memorials: list[GeneratedMemorialResponse]


class GeneratedMemorialDownloadResponse(BaseModel):
    download_url: str
