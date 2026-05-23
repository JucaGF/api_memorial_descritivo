from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.schemas.generated_memorial import GeneratedMemorialResponse
from app.services.review_items import build_review_items

_client_instance: Any = None
logger = logging.getLogger(__name__)

GENERATED_MEMORIALS_TABLE = "generated_memorials"
STATUS_PROCESSING = "processing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"

_FILENAME_BY_TYPE = {
    "eletrico": "memorial_eletrico_v1.docx",
    "telecom": "memorial_telecom_v1.docx",
    "gas-natural": "memorial_gas_natural_v1.docx",
    "glp": "memorial_glp_v1.docx",
    "glp_v2": "memorial_glp_v2.docx",
}


class GeneratedMemorialStorageError(RuntimeError):
    """Safe application error for generated memorial storage failures."""


class GeneratedMemorialArtifactNotFoundError(GeneratedMemorialStorageError):
    """Raised when the registered artifact no longer exists in storage."""


def _storage_settings():
    return get_settings().generated_memorial_storage


def _client() -> Any:
    global _client_instance
    if _client_instance is None:
        from supabase import create_client

        settings = _storage_settings()
        _client_instance = create_client(
            settings.supabase_url,
            settings.supabase_key,
        )
    return _client_instance


def _signed_url_from_response(response: Any) -> str:
    if isinstance(response, dict):
        return response.get("signedURL") or response.get("signed_url") or response.get("url") or ""
    signed_url = getattr(response, "signed_url", None) or getattr(response, "signedURL", None)
    return signed_url or ""


def _expected_storage_path(memorial_type: str, memorial_id: str) -> str:
    filename = _FILENAME_BY_TYPE[memorial_type]
    return f"{memorial_type}/{memorial_id}/{filename}"


def _safe_record_storage_path(record: dict[str, Any]) -> str:
    memorial_id = str(record.get("id", "")).strip()
    memorial_type = str(record.get("type", "")).strip()
    storage_bucket = str(record.get("storage_bucket", "")).strip()
    storage_path = str(record.get("storage_path", "")).strip()

    if memorial_type not in _FILENAME_BY_TYPE:
        raise GeneratedMemorialStorageError("Tipo de memorial persistido inválido.")
    if not memorial_id or not storage_path:
        raise GeneratedMemorialStorageError("Registro de memorial persistido inválido.")
    if storage_bucket != _storage_settings().bucket:
        raise GeneratedMemorialStorageError("Bucket de memorial persistido inválido.")

    expected_path = _expected_storage_path(memorial_type, memorial_id)
    if storage_path != expected_path:
        raise GeneratedMemorialStorageError("Path de memorial persistido inválido.")

    return storage_path


def _is_missing_artifact_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(fragment in message for fragment in ("not found", "no such", "does not exist", "missing"))


def _update_generated_memorial_status(
    memorial_id: str,
    *,
    status: str,
    updated_at: str,
) -> None:
    (
        _client()
        .table(GENERATED_MEMORIALS_TABLE)
        .update({"status": status, "updated_at": updated_at})
        .eq("id", memorial_id)
        .execute()
    )


def _remove_artifact_if_present(storage_bucket: str, storage_path: str) -> None:
    try:
        _client().storage.from_(storage_bucket).remove([storage_path])
    except Exception as error:
        logger.warning(
            "Generated memorial cleanup failed memorial_path=%s error_type=%s",
            storage_path,
            type(error).__name__,
        )


def create_signed_download_url(record: dict[str, Any]) -> str:
    storage_path = _safe_record_storage_path(record)
    try:
        response = (
            _client()
            .storage
            .from_(record["storage_bucket"])
            .create_signed_url(storage_path, _storage_settings().signed_url_ttl_seconds)
        )
    except Exception as error:
        if _is_missing_artifact_error(error):
            raise GeneratedMemorialArtifactNotFoundError(
                "Arquivo do memorial não está mais disponível."
            ) from error
        raise GeneratedMemorialStorageError(
            "Falha ao criar URL de download do memorial."
        ) from error

    signed_url = _signed_url_from_response(response)
    if not signed_url:
        raise GeneratedMemorialArtifactNotFoundError(
            "Arquivo do memorial não está mais disponível."
        )
    return signed_url


def _response_from_record(
    record: dict[str, Any],
    *,
    include_download_url: bool = True,
    include_context: bool = False,
    include_report: bool = True,
) -> GeneratedMemorialResponse:
    download_url = (
        create_signed_download_url(record)
        if include_download_url and record.get("status") == STATUS_READY
        else ""
    )
    payload: dict[str, Any] = {
        "id": str(record["id"]),
        "type": record["type"],
        "project_name": record["project_name"],
        "status": record["status"],
        "observations": record.get("observations"),
        "pdf_filenames": record.get("pdf_filenames") or [],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "download_url": download_url,
        "context_version": record.get("context_version"),
        "template_version": record.get("template_version"),
    }
    if include_context:
        payload["final_context"] = record.get("final_context")
    if include_context or include_report:
        payload["extraction_report"] = record.get("extraction_report")
        payload["conflicts"] = record.get("conflicts") or []
    payload["review_items"] = build_review_items(
        record.get("final_context"),
        record.get("extraction_report"),
    )
    return GeneratedMemorialResponse.model_validate(payload)


def create_generated_memorial(
    *,
    memorial_type: str,
    project_name: str,
    output_path: Path,
    pdf_filenames: list[str],
    observations: str | None = None,
    final_context: dict[str, Any] | None = None,
    extraction_report: dict[str, Any] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    context_version: str | None = None,
    template_version: str | None = None,
) -> GeneratedMemorialResponse:
    memorial_id = str(uuid.uuid4())
    storage_settings = _storage_settings()
    storage_path = _expected_storage_path(memorial_type, memorial_id)
    now = datetime.now(tz=timezone.utc).isoformat()

    record: dict[str, Any] = {
        "id": memorial_id,
        "type": memorial_type,
        "project_name": project_name,
        "status": STATUS_PROCESSING,
        "observations": observations,
        "pdf_filenames": pdf_filenames,
        "storage_bucket": storage_settings.bucket,
        "storage_path": storage_path,
        "created_at": now,
        "updated_at": now,
        "final_context": final_context,
        "extraction_report": extraction_report,
        "conflicts": conflicts if conflicts is not None else [],
        "context_version": context_version,
        "template_version": template_version,
    }
    _client().table(GENERATED_MEMORIALS_TABLE).insert(record).execute()

    try:
        _client().storage.from_(storage_settings.bucket).upload(
            storage_path,
            output_path.read_bytes(),
            {
                "content-type": (
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ),
                "upsert": "false",
            },
        )
        _update_generated_memorial_status(
            memorial_id,
            status=STATUS_READY,
            updated_at=now,
        )
    except Exception as error:
        _remove_artifact_if_present(storage_settings.bucket, storage_path)
        try:
            _update_generated_memorial_status(
                memorial_id,
                status=STATUS_FAILED,
                updated_at=now,
            )
        except Exception as update_error:
            logger.warning(
                "Generated memorial failure status update failed memorial_id=%s error_type=%s",
                memorial_id,
                type(update_error).__name__,
            )
        raise GeneratedMemorialStorageError(
            "Falha ao persistir memorial gerado."
        ) from error

    return _response_from_record(
        {**record, "status": STATUS_READY},
        include_context=False,
        include_report=True,
    )


def list_generated_memorials(memorial_type: str | None = None) -> list[GeneratedMemorialResponse]:
    query = _client().table(GENERATED_MEMORIALS_TABLE).select("*").order("created_at", desc=True)
    if memorial_type:
        response = query.eq("type", memorial_type).execute()
    else:
        response = query.execute()
    return [
        _response_from_record(record, include_download_url=False, include_context=False)
        for record in (response.data or [])
    ]


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


def get_generated_memorial(
    memorial_id: str,
    *,
    include_context: bool = False,
) -> GeneratedMemorialResponse | None:
    record = get_generated_memorial_record(memorial_id)
    if record is None:
        return None
    return _response_from_record(record, include_context=include_context)


def delete_generated_memorial(memorial_id: str) -> bool:
    record = get_generated_memorial_record(memorial_id)
    if record is None:
        return False

    storage_path = _safe_record_storage_path(record)
    try:
        _client().storage.from_(record["storage_bucket"]).remove([storage_path])
    except Exception as error:
        if _is_missing_artifact_error(error):
            raise GeneratedMemorialArtifactNotFoundError(
                "Arquivo do memorial não está mais disponível."
            ) from error
        raise GeneratedMemorialStorageError(
            "Falha ao excluir arquivo do memorial."
        ) from error
    _client().table(GENERATED_MEMORIALS_TABLE).delete().eq("id", memorial_id).execute()
    return True
