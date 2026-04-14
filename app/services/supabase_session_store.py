from __future__ import annotations

import os
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

# Imports from session_store are safe here: this module is only imported at the
# bottom of session_store.py, after ReviewSession and constants are already defined.
from app.services.session_store import (
    ReviewSession,
    _SESSION_TTL,
    STATUS_PROCESSING,
    _is_session_expired,
)

_client_instance: Any = None


def _client() -> Any:
    global _client_instance
    if _client_instance is None:
        from supabase import create_client
        _client_instance = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )
    return _client_instance


def create_session() -> str:
    session_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc)
    _client().table("review_sessions").insert({
        "session_id": session_id,
        "status": STATUS_PROCESSING,
        "created_at": now.isoformat(),
        "expires_at": (now + _SESSION_TTL).isoformat(),
        "partial_context": {},
        "extraction_report": {},
        "corrections": {},
        "error": None,
    }).execute()
    return session_id


def load_session(session_id: str) -> ReviewSession | None:
    response = (
        _client()
        .table("review_sessions")
        .select("*")
        .eq("session_id", session_id)
        .execute()
    )
    if not response.data:
        return None
    session = ReviewSession(**response.data[0])
    if _is_session_expired(session):
        delete_session(session_id)
        return None
    return session


def save_session(session: ReviewSession) -> None:
    _client().table("review_sessions").upsert(asdict(session)).execute()


def update_session(session_id: str, **kwargs: Any) -> ReviewSession | None:
    session = load_session(session_id)
    if session is None:
        return None
    data = asdict(session)
    data.update(kwargs)
    updated = ReviewSession(**data)
    _client().table("review_sessions").update(kwargs).eq("session_id", session_id).execute()
    return updated


def delete_session(session_id: str) -> None:
    _client().table("review_sessions").delete().eq("session_id", session_id).execute()
