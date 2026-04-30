from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import gettempdir
from typing import Any

from app.services.generated_memorial_store import GENERATED_MEMORIALS_BUCKET
from app.services.memorial_renderer import (
    ELETRICO_V1_TEMPLATE_PATH,
    GAS_NATURAL_V1_TEMPLATE_PATH,
    GLP_V1_TEMPLATE_PATH,
    TELECOM_V1_TEMPLATE_PATH,
)
from app.services.memorial_validator import (
    ELETRICO_V1_SCHEMA_PATH,
    GAS_NATURAL_V1_SCHEMA_PATH,
    GLP_V1_SCHEMA_PATH,
    TELECOM_V1_SCHEMA_PATH,
)
from app.services.session_store import _sessions_dir


def _utc_timestamp() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _build_check(
    name: str,
    status: str,
    *,
    detail: str | None = None,
) -> dict[str, str]:
    check = {"name": name, "status": status}
    if detail:
        check["detail"] = detail
    return check


def get_liveness_payload() -> dict[str, Any]:
    return {
        "status": "ok",
        "timestamp": _utc_timestamp(),
        "checks": [_build_check("app", "ok")],
    }


def _required_template_paths() -> list[Path]:
    return [
        ELETRICO_V1_TEMPLATE_PATH,
        TELECOM_V1_TEMPLATE_PATH,
        GAS_NATURAL_V1_TEMPLATE_PATH,
        GLP_V1_TEMPLATE_PATH,
    ]


def _required_schema_paths() -> list[Path]:
    return [
        ELETRICO_V1_SCHEMA_PATH,
        TELECOM_V1_SCHEMA_PATH,
        GAS_NATURAL_V1_SCHEMA_PATH,
        GLP_V1_SCHEMA_PATH,
    ]


def _check_templates() -> dict[str, str]:
    missing = [
        str(path.relative_to(path.parents[2]))
        for path in _required_template_paths() + _required_schema_paths()
        if not path.is_file()
    ]
    if missing:
        return _build_check("templates", "error", detail="required files missing")
    return _build_check("templates", "ok")


def _is_directory_writable(path: Path) -> bool:
    path.mkdir(parents=True, exist_ok=True)
    return path.is_dir() and os.access(path, os.W_OK)


def _check_storage() -> dict[str, str]:
    required_dirs = [Path(gettempdir()), _sessions_dir()]
    for path in required_dirs:
        if not _is_directory_writable(path):
            return _build_check("storage", "error", detail="required directory unavailable")
    return _build_check("storage", "ok")


def _check_configuration() -> dict[str, str]:
    if not GENERATED_MEMORIALS_BUCKET.strip():
        return _build_check("configuration", "error", detail="generated memorials bucket missing")
    return _build_check("configuration", "ok")


def _check_session_backend() -> dict[str, str]:
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_KEY", "").strip()
    if not supabase_url and not supabase_key:
        return _build_check("session_backend", "skipped", detail="filesystem mode")
    if not supabase_url or not supabase_key:
        return _build_check("session_backend", "error", detail="incomplete supabase configuration")

    try:
        from supabase import create_client

        create_client(supabase_url, supabase_key)
    except Exception:
        return _build_check("session_backend", "error", detail="supabase client initialization failed")
    return _build_check("session_backend", "ok", detail="supabase configured")


def get_readiness_payload() -> dict[str, Any]:
    checks = [
        _build_check("app", "ok"),
        _check_templates(),
        _check_storage(),
        _check_configuration(),
        _check_session_backend(),
    ]
    status = "ok" if all(check["status"] in {"ok", "skipped"} for check in checks) else "error"
    return {
        "status": status,
        "timestamp": _utc_timestamp(),
        "checks": checks,
    }
