from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

_SESSIONS_DIR_ENV = os.getenv("SESSIONS_DIR", "sessions")
_SESSION_TTL = timedelta(hours=24)

STATUS_PROCESSING = "processing"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_FAILED = "failed"


@dataclass
class ReviewSession:
    session_id: str
    status: str
    created_at: str
    expires_at: str
    partial_context: dict[str, Any] = field(default_factory=dict)
    extraction_report: dict[str, Any] = field(default_factory=dict)
    corrections: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _sessions_dir() -> Any:
    from pathlib import Path
    return Path(_SESSIONS_DIR_ENV)


def _session_path(session_id: str) -> Any:
    return _sessions_dir() / f"{session_id}.json"


def _ensure_dir() -> None:
    _sessions_dir().mkdir(parents=True, exist_ok=True)


def create_session() -> str:
    _ensure_dir()
    session_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    session = ReviewSession(
        session_id=session_id,
        status=STATUS_PROCESSING,
        created_at=now.isoformat(),
        expires_at=(now + _SESSION_TTL).isoformat(),
    )
    _session_path(session_id).write_text(
        json.dumps(asdict(session), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return session_id


def load_session(session_id: str) -> ReviewSession | None:
    path = _session_path(session_id)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return ReviewSession(**data)


def save_session(session: ReviewSession) -> None:
    _ensure_dir()
    _session_path(session.session_id).write_text(
        json.dumps(asdict(session), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def update_session(session_id: str, **kwargs: Any) -> ReviewSession | None:
    session = load_session(session_id)
    if session is None:
        return None
    data = asdict(session)
    data.update(kwargs)
    updated = ReviewSession(**data)
    save_session(updated)
    return updated


def delete_session(session_id: str) -> None:
    _session_path(session_id).unlink(missing_ok=True)


# ── Backend override ──────────────────────────────────────────────────────────
# When SUPABASE_URL + SUPABASE_KEY are set, replace filesystem functions with
# Supabase implementations. All callers (routes.py, tests) are unaffected.
import os as _os  # noqa: E402

if _os.getenv("SUPABASE_URL") and _os.getenv("SUPABASE_KEY"):
    try:
        from app.services.supabase_session_store import (  # noqa: F401, F811
            create_session,
            delete_session,
            load_session,
            save_session,
            update_session,
        )
    except ImportError:
        pass  # supabase package not installed — keep filesystem backend
