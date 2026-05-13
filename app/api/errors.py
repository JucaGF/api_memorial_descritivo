from __future__ import annotations

import os
import re
import traceback
from typing import Any

from fastapi.responses import JSONResponse
from starlette.requests import Request

REQUEST_ID_HEADER = "X-Request-ID"
INTERNAL_SERVER_ERROR_MESSAGE = "Erro interno ao processar a requisição."
VALIDATION_ERROR_MESSAGE = "Dados inválidos na requisição."

_SECRET_ENV_NAMES = (
    "OPENAI_API_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
    "DATABASE_URL",
)
_SENSITIVE_ASSIGNMENT_PATTERNS = (
    re.compile(r"(?i)\b(authorization|cookie|set-cookie)\b\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\b(token|password|senha)\b\s*[:=]\s*[^\s,;]+"),
    re.compile(
        r"(?i)\b(openai_api_key|supabase_service_role_key|supabase_anon_key|database_url)\b\s*[:=]\s*[^\s,;]+"
    ),
)


def get_request_id(request: Request | None) -> str | None:
    return getattr(getattr(request, "state", None), "request_id", None)


def build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None,
    details: Any | None = None,
    detail: Any | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }
    if request_id is not None:
        error["request_id"] = request_id
    if details is not None:
        error["details"] = details

    content: dict[str, Any] = {
        "detail": message if detail is None else detail,
        "error": error,
    }
    response = JSONResponse(status_code=status_code, content=content)
    if request_id is not None:
        response.headers[REQUEST_ID_HEADER] = request_id
    return response


def build_internal_server_error_response(request: Request) -> JSONResponse:
    return build_error_response(
        status_code=500,
        code="internal_server_error",
        message=INTERNAL_SERVER_ERROR_MESSAGE,
        request_id=get_request_id(request),
    )


def build_memorial_validation_error_response(
    *,
    request: Request | None,
    detail: str,
    issues: list[dict[str, Any]],
    extraction_report: Any | None = None,
) -> JSONResponse:
    """Memorial validation error envelope.

    Preserves the legacy fields (`detail`, `errors`, optional `extraction_report`)
    used by existing clients while also exposing the unified `error` object with
    `code="memorial_validation_error"` and `request_id`. Both shapes can be read
    simultaneously without breaking the older contract.
    """
    request_id = get_request_id(request)
    error: dict[str, Any] = {
        "code": "memorial_validation_error",
        "message": detail,
    }
    if request_id is not None:
        error["request_id"] = request_id
    error["details"] = {"issues": issues}
    if extraction_report is not None:
        error["details"]["extraction_report"] = extraction_report

    content: dict[str, Any] = {
        "detail": detail,
        "errors": issues,
        "error": error,
    }
    if extraction_report is not None:
        content["extraction_report"] = extraction_report

    response = JSONResponse(status_code=400, content=content)
    if request_id is not None:
        response.headers[REQUEST_ID_HEADER] = request_id
    return response


def build_client_error_response(
    *,
    request: Request | None,
    status_code: int,
    code: str,
    message: str,
    detail: str | None = None,
    details: Any | None = None,
) -> JSONResponse:
    """Standard client error (400/404/409/etc.) with request_id."""
    return build_error_response(
        status_code=status_code,
        code=code,
        message=message,
        request_id=get_request_id(request),
        detail=detail,
        details=details,
    )


def sanitize_text(value: str) -> str:
    sanitized = value
    for env_name in _SECRET_ENV_NAMES:
        env_value = os.getenv(env_name)
        if env_value:
            sanitized = sanitized.replace(env_value, "[REDACTED]")
    for pattern in _SENSITIVE_ASSIGNMENT_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def format_sanitized_exception_trace(exc: Exception) -> str:
    formatted = "".join(
        traceback.TracebackException.from_exception(
            exc,
            capture_locals=False,
        ).format()
    )
    return sanitize_text(formatted)
