from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas.generated_memorial import GeneratedMemorialResponse

_client_instance: Any = None

GENERATED_MEMORIALS_TABLE = "generated_memorials"
GENERATED_MEMORIALS_BUCKET = os.getenv(
    "GENERATED_MEMORIALS_BUCKET",
    "generated-memorials",
)
SIGNED_URL_TTL_SECONDS = int(os.getenv("GENERATED_MEMORIALS_SIGNED_URL_TTL", "3600"))

_FILENAME_BY_TYPE = {
    "eletrico": "memorial_eletrico_v1.docx",
    "telecom": "memorial_telecom_v1.docx",
    "gas-natural": "memorial_gas_natural_v1.docx",
    "glp": "memorial_glp_v1.docx",
}


def _client() -> Any:
    global _client_instance
    if _client_instance is None:
        from supabase import create_client

        _client_instance = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_KEY"],
        )
    return _client_instance


def _signed_url_from_response(response: Any) -> str:
    if isinstance(response, dict):
        return response.get("signedURL") or response.get("signed_url") or response.get("url") or ""
    signed_url = getattr(response, "signed_url", None) or getattr(response, "signedURL", None)
    return signed_url or ""


def create_signed_download_url(record: dict[str, Any]) -> str:
    response = (
        _client()
        .storage
        .from_(record["storage_bucket"])
        .create_signed_url(record["storage_path"], SIGNED_URL_TTL_SECONDS)
    )
    return _signed_url_from_response(response)


def _response_from_record(record: dict[str, Any]) -> GeneratedMemorialResponse:
    return GeneratedMemorialResponse.model_validate(
        {
            "id": str(record["id"]),
            "type": record["type"],
            "project_name": record["project_name"],
            "status": record["status"],
            "observations": record.get("observations"),
            "pdf_filenames": record.get("pdf_filenames") or [],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "download_url": create_signed_download_url(record),
        }
    )


def create_generated_memorial(
    *,
    memorial_type: str,
    project_name: str,
    output_path: Path,
    pdf_filenames: list[str],
    observations: str | None = None,
) -> GeneratedMemorialResponse:
    memorial_id = str(uuid.uuid4())
    filename = _FILENAME_BY_TYPE[memorial_type]
    storage_path = f"{memorial_type}/{memorial_id}/{filename}"
    now = datetime.now(tz=timezone.utc).isoformat()

    _client().storage.from_(GENERATED_MEMORIALS_BUCKET).upload(
        storage_path,
        output_path.read_bytes(),
        {
            "content-type": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            "upsert": "false",
        },
    )

    record = {
        "id": memorial_id,
        "type": memorial_type,
        "project_name": project_name,
        "status": "ready",
        "observations": observations,
        "pdf_filenames": pdf_filenames,
        "storage_bucket": GENERATED_MEMORIALS_BUCKET,
        "storage_path": storage_path,
        "created_at": now,
        "updated_at": now,
    }
    _client().table(GENERATED_MEMORIALS_TABLE).insert(record).execute()
    return _response_from_record(record)


def list_generated_memorials(memorial_type: str | None = None) -> list[GeneratedMemorialResponse]:
    query = _client().table(GENERATED_MEMORIALS_TABLE).select("*").order("created_at", desc=True)
    if memorial_type:
        response = query.eq("type", memorial_type).execute()
    else:
        response = query.execute()
    return [_response_from_record(record) for record in (response.data or [])]


def get_generated_memorial_record(memorial_id: str) -> dict[str, Any] | None:
    response = (
        _client()
        .table(GENERATED_MEMORIALS_TABLE)
        .select("*")
        .eq("id", memorial_id)
        .execute()
    )
    if not response.data:
        return None
    return response.data[0]


def get_generated_memorial(memorial_id: str) -> GeneratedMemorialResponse | None:
    record = get_generated_memorial_record(memorial_id)
    if record is None:
        return None
    return _response_from_record(record)
