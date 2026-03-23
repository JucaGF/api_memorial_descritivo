from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SessionCreatedResponse(BaseModel):
    session_id: str
    status: str


class SessionStateResponse(BaseModel):
    session_id: str
    status: str
    created_at: str
    expires_at: str
    partial_context: dict[str, Any]
    extraction_report: dict[str, Any]
    corrections: dict[str, Any]
    error: str | None = None


class ContextCorrectionsPayload(BaseModel):
    corrections: dict[str, Any]
