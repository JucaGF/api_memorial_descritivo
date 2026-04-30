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
