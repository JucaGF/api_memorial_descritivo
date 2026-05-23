from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ReviewItemResponse(BaseModel):
    id: str
    category: str
    field_path: str
    label: str
    current_value: Any = None
    confidence: str | None = None
    evidence: str | None = None
    rule: str | None = None
    reason: str | None = None
    editable_type: str


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
    review_items: list[ReviewItemResponse] | None = None


class GeneratedMemorialListResponse(BaseModel):
    memorials: list[GeneratedMemorialResponse]


class GeneratedMemorialDownloadResponse(BaseModel):
    download_url: str


class MemorialCorrectionsPayload(BaseModel):
    corrections: dict[str, Any]
