from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FieldExtractionResponse(BaseModel):
    value: Any
    rule: str
    evidence: str | None = None
    confidence: str = "medium"


class ExtractionReportResponse(BaseModel):
    filled: list[str]
    missing: list[str]
    pending: list[str]
    evidence: dict[str, FieldExtractionResponse] = Field(default_factory=dict)


class SessionCreatedResponse(BaseModel):
    session_id: str
    status: str


class SessionStateResponse(BaseModel):
    session_id: str
    status: str
    created_at: str
    expires_at: str
    partial_context: dict[str, Any]
    extraction_report: ExtractionReportResponse | dict[str, Any]
    corrections: dict[str, Any]
    error: str | None = None


class ContextCorrectionsPayload(BaseModel):
    corrections: dict[str, Any]
