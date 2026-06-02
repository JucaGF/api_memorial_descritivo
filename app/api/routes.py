from __future__ import annotations

import json
import logging
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from app.api.errors import (
    build_client_error_response,
    build_error_response,
    build_internal_server_error_response,
    build_memorial_validation_error_response,
    format_sanitized_exception_trace,
    get_request_id,
)
from app.api.auth import CurrentUser, require_owner, require_user
from app.config import get_settings
from app.schemas.file_ingestion import FileIngestionResponse
from app.schemas.generated_memorial import (
    GeneratedMemorialDownloadResponse,
    GeneratedMemorialListResponse,
    GeneratedMemorialResponse,
    MemorialCorrectionsPayload,
)
from app.schemas.user import (
    AdminUserListResponse,
    CreateAdminUserPayload,
    CurrentUserResponse,
    UpdateAdminUserPayload,
    UpdateMyProfilePayload,
    UserProfileResponse,
)
from app.schemas.review_session import (
    ContextCorrectionsPayload,
    SessionCreatedResponse,
    SessionStateResponse,
)
from app.services.context_builder import merge_context
from app.services.file_ingestion import (
    FileIngestionError,
    FileIngestionResult,
    UploadFileTooLargeError,
    UploadTooManyFilesError,
    UploadTooManyPagesError,
    UploadTotalTooLargeError,
    cleanup_ingestion_result,
    ingest_uploaded_files,
)
from app.services.memorial_renderer import MemorialRenderError, GLP_V2_TEMPLATE_PATH
from app.services.memorial_validator import MemorialValidationError
from app.services.generated_memorial_store import (
    GeneratedMemorialArtifactNotFoundError,
    GeneratedMemorialStorageError,
    create_generated_memorial,
    create_signed_download_url,
    delete_generated_memorial,
    get_generated_memorial,
    get_generated_memorial_record,
    list_generated_memorials,
)
from app.services.health import get_liveness_payload, get_readiness_payload
from app.services.pipeline import (
    generate_memorial_eletrico_v1,
    generate_memorial_gas_natural_v1,
    generate_memorial_glp_v1,
    generate_memorial_glp_v2,
    generate_memorial_telecom_v1,
)
from app.services.pipeline_from_files import (
    extract_mapping_from_ingested_files,
    generate_memorial_gas_natural_v1_from_uploaded_files,
    generate_memorial_glp_v1_from_uploaded_files,
    generate_memorial_glp_v2_from_uploaded_files,
    generate_memorial_telecom_v1_from_uploaded_files,
    generate_memorial_eletrico_v1_from_uploaded_files,
)
from app.services.project_extractor import ProjectExtractionError
from app.services.session_store import (
    STATUS_FAILED,
    STATUS_PENDING_REVIEW,
    create_session,
    delete_session,
    load_session,
    update_session,
)
from app.services.supabase_auth_admin import (
    SupabaseAuthAdminError,
    SupabaseAuthUserAlreadyExistsError,
    create_auth_user,
    delete_auth_user,
)
from app.services.user_profile_store import (
    DuplicateUserProfileError,
    LastOwnerError,
    SelfManagementError,
    UserProfile,
    UserProfileError,
    UserProfileNotFoundError,
    create_profile,
    list_profiles,
    update_my_display_name,
    update_profile_as_owner,
    validate_profile_removal_as_owner,
)

logger = logging.getLogger(__name__)

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

router = APIRouter()

_SUPPORTED_MEMORIAL_TYPES = {"eletrico", "telecom", "gas-natural", "glp"}
_SUPPORTED_MEMORIAL_LIST_TYPES = _SUPPORTED_MEMORIAL_TYPES | {"glp_v2"}
_PROJECT_NAME_BY_TYPE = {
    "eletrico": "Memorial Elétrico",
    "telecom": "Memorial Telecom",
    "gas-natural": "Memorial Gás Natural",
    "glp": "Memorial GLP",
    "glp_v2": "Memorial GLP v2",
}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/live")
def health_live():
    return get_liveness_payload()


@router.get("/health/ready")
def health_ready():
    payload = get_readiness_payload()
    status_code = 200 if payload["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=payload)


def _profile_response(profile: UserProfile | CurrentUser) -> UserProfileResponse:
    return UserProfileResponse.model_validate(
        {
            "user_id": profile.user_id,
            "email": profile.email,
            "display_name": profile.display_name,
            "role": profile.role,
            "status": profile.status,
            "created_at": getattr(profile, "created_at", None),
            "updated_at": getattr(profile, "updated_at", None),
        }
    )


@router.get("/api/v1/me", response_model=CurrentUserResponse)
def get_current_user_profile(
    current_user: CurrentUser = Depends(require_user),
):
    return CurrentUserResponse.model_validate(_profile_response(current_user).model_dump())


@router.patch("/api/v1/me", response_model=CurrentUserResponse)
def update_current_user_profile(
    payload: UpdateMyProfilePayload,
    request: Request,
    current_user: CurrentUser = Depends(require_user),
):
    try:
        profile = update_my_display_name(current_user.user_id, payload.display_name)
        return CurrentUserResponse.model_validate(_profile_response(profile).model_dump())
    except UserProfileError as error:
        return build_client_error_response(
            request=request,
            status_code=400,
            code="user_profile_update_failed",
            message=str(error),
        )


@router.get("/api/v1/admin/users", response_model=AdminUserListResponse)
def list_admin_users(
    current_user: CurrentUser = Depends(require_owner),
):
    return AdminUserListResponse(
        users=[_profile_response(profile) for profile in list_profiles()]
    )


@router.post(
    "/api/v1/admin/users",
    response_model=UserProfileResponse,
    status_code=201,
)
def create_admin_user(
    payload: CreateAdminUserPayload,
    request: Request,
    current_user: CurrentUser = Depends(require_owner),
):
    auth_user = None
    try:
        auth_user = create_auth_user(
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name,
            role=payload.role,
        )
        profile = create_profile(
            user_id=auth_user.user_id,
            email=auth_user.email,
            display_name=payload.display_name,
            role=payload.role,
            created_by=current_user.user_id,
        )
        return _profile_response(profile)
    except (SupabaseAuthUserAlreadyExistsError, DuplicateUserProfileError) as error:
        return build_client_error_response(
            request=request,
            status_code=409,
            code="admin_user_already_exists",
            message=str(error),
        )
    except (SupabaseAuthAdminError, UserProfileError) as error:
        if auth_user is not None:
            try:
                delete_auth_user(auth_user.user_id)
            except SupabaseAuthAdminError:
                logger.warning(
                    "Auth user cleanup failed after profile creation error user_id=%s",
                    auth_user.user_id,
                )
        return build_error_response(
            status_code=503,
            code="admin_user_create_failed",
            message=str(error),
            request_id=get_request_id(request),
        )


@router.patch("/api/v1/admin/users/{user_id}", response_model=UserProfileResponse)
def update_admin_user(
    user_id: str,
    payload: UpdateAdminUserPayload,
    request: Request,
    current_user: CurrentUser = Depends(require_owner),
):
    try:
        profile = update_profile_as_owner(
            target_user_id=user_id,
            actor_user_id=current_user.user_id,
            display_name=payload.display_name,
            role=payload.role,
            status=payload.status,
        )
        return _profile_response(profile)
    except UserProfileNotFoundError:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="admin_user_not_found",
            message="Usuário não encontrado.",
        )
    except (SelfManagementError, LastOwnerError, UserProfileError) as error:
        return build_client_error_response(
            request=request,
            status_code=409,
            code="admin_user_update_not_allowed",
            message=str(error),
        )


@router.delete("/api/v1/admin/users/{user_id}", response_model=UserProfileResponse)
def delete_admin_user(
    user_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_owner),
):
    try:
        profile = validate_profile_removal_as_owner(user_id, current_user.user_id)
        delete_auth_user(user_id)
        return _profile_response(profile)
    except UserProfileNotFoundError:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="admin_user_not_found",
            message="Usuário não encontrado.",
        )
    except (SelfManagementError, LastOwnerError, UserProfileError) as error:
        return build_client_error_response(
            request=request,
            status_code=409,
            code="admin_user_delete_not_allowed",
            message=str(error),
        )
    except SupabaseAuthAdminError as error:
        return build_error_response(
            status_code=503,
            code="admin_user_delete_failed",
            message=str(error),
            request_id=get_request_id(request),
        )


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _validation_error_response(
    error: MemorialValidationError,
    detail: str,
    request: Request | None = None,
) -> JSONResponse:
    if _is_unresolved_quantitative_conflict(error):
        return _quantitative_conflict_error_response(error, request)

    issues = [
        {
            "path": issue.path,
            "message": issue.message,
            "validator": issue.validator,
        }
        for issue in error.issues
    ]
    return build_memorial_validation_error_response(
        request=request,
        detail=detail,
        issues=issues,
        extraction_report=error.extraction_report,
    )


def _docx_file_response(
    output_path: Path,
    background_tasks: BackgroundTasks,
    filename: str,
) -> FileResponse:
    background_tasks.add_task(_remove_file, output_path)
    return FileResponse(
        path=output_path,
        media_type=DOCX_MEDIA_TYPE,
        filename=filename,
    )


def _file_ingestion_response(result) -> FileIngestionResponse:
    return FileIngestionResponse.model_validate(
        {
            "files": [
                {
                    "filename": file.original_filename,
                    "content_type": file.content_type,
                    "extension": file.extension,
                    "size_bytes": file.size_bytes,
                }
                for file in result.files
            ]
        }
    )


def _unsupported_memorial_type_response(
    memorial_type: str,
    request: Request | None = None,
) -> JSONResponse:
    detail = f"Tipo de memorial não encontrado: {memorial_type}."
    return build_client_error_response(
        request=request,
        status_code=404,
        code="unsupported_memorial_type",
        message=detail,
        detail=detail,
        details={"memorial_type": memorial_type},
    )


_UPLOAD_LIMIT_ERRORS = (
    UploadFileTooLargeError,
    UploadTotalTooLargeError,
    UploadTooManyFilesError,
    UploadTooManyPagesError,
)


def _ingestion_error_status_code(error: FileIngestionError) -> int:
    """413 for size/count violations, 400 for shape/content violations."""
    return 413 if isinstance(error, _UPLOAD_LIMIT_ERRORS) else 400


_TEMPLATE_VERSION_BY_TYPE = {
    "eletrico": "eletrico_v1",
    "telecom": "telecom_v1",
    "gas-natural": "gas_natural_v1",
    "glp": "glp_v1",
}
_CONTEXT_VERSION_BY_TYPE = _TEMPLATE_VERSION_BY_TYPE
_CONTEXT_VERSION_BY_TYPE["glp_v2"] = "glp_v2"
_TEMPLATE_VERSION_BY_TYPE["glp_v2"] = "glp_v2"


async def _generate_memorial_from_uploaded_files(
    memorial_type: str,
    files: list[UploadFile],
    output_path: Path,
):
    if memorial_type == "eletrico":
        return await generate_memorial_eletrico_v1_from_uploaded_files(files, output_path)
    if memorial_type == "telecom":
        return await generate_memorial_telecom_v1_from_uploaded_files(files, output_path)
    if memorial_type == "gas-natural":
        return await generate_memorial_gas_natural_v1_from_uploaded_files(files, output_path)
    if memorial_type == "glp":
        return await generate_memorial_glp_v1_from_uploaded_files(files, output_path)
    raise ValueError(f"Tipo de memorial não suportado: {memorial_type}.")


def _generate_memorial_from_context(
    memorial_type: str,
    context: dict[str, Any],
    output_path: Path,
):
    if memorial_type == "eletrico":
        return generate_memorial_eletrico_v1(context, output_path)
    if memorial_type == "telecom":
        return generate_memorial_telecom_v1(context, output_path)
    if memorial_type == "gas-natural":
        return generate_memorial_gas_natural_v1(context, output_path)
    if memorial_type == "glp":
        return generate_memorial_glp_v1(context, output_path)
    if memorial_type == "glp_v2":
        return generate_memorial_glp_v2(context, output_path)
    raise ValueError(f"Tipo de memorial não suportado: {memorial_type}.")


def _flatten_corrections(
    corrections: dict[str, Any],
    prefix: str = "",
) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in corrections.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            flattened.update(_flatten_corrections(value, path))
        else:
            flattened[path] = value
    return flattened


def _report_with_user_corrections(
    extraction_report: dict[str, Any] | None,
    corrections: dict[str, Any],
) -> dict[str, Any]:
    report = deepcopy(extraction_report) if isinstance(extraction_report, dict) else {}
    existing = report.get("user_corrections")
    user_corrections = existing if isinstance(existing, dict) else {}
    user_corrections.update(_flatten_corrections(corrections))
    report["user_corrections"] = user_corrections
    return report


def _extraction_report_to_jsonable(report: Any) -> dict[str, Any] | None:
    """Convert ExtractionReport dataclass (or already-dict) into a JSON-friendly payload.

    The dashboard/chatbot/site read this payload via the persisted memorial API to
    surface evidence and conflicts that produced the rendered DOCX.
    """
    if report is None:
        return None
    if isinstance(report, dict):
        return report
    from dataclasses import asdict, is_dataclass

    if is_dataclass(report):
        return asdict(report)
    return None


def _extract_conflicts_from_report(extraction_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not extraction_report:
        return []
    conflicts = extraction_report.get("conflicts")
    if isinstance(conflicts, list):
        return conflicts
    cross_validation = extraction_report.get("cross_validation")
    if isinstance(cross_validation, dict):
        inner = cross_validation.get("conflicts")
        if isinstance(inner, list):
            return inner
        quantitative_conflicts = cross_validation.get("quantitative_conflicts")
        if isinstance(quantitative_conflicts, list):
            return quantitative_conflicts
    return []


def _is_unresolved_quantitative_conflict(error: MemorialValidationError) -> bool:
    if not isinstance(error.extraction_report, dict):
        return False
    conflicts = _extract_conflicts_from_report(error.extraction_report)
    return any(
        isinstance(conflict, dict)
        and conflict.get("status") == "unresolved"
        and (
            "quantitative" in str(conflict.get("tipo", ""))
            or "total" in str(conflict.get("tipo", ""))
            or str(conflict.get("tipo", "")).startswith(
                ("glp_", "gas_", "eletrico_", "telecom_")
            )
        )
        for conflict in conflicts
    )


def _quantitative_conflict_error_response(
    error: MemorialValidationError,
    request: Request | None,
) -> JSONResponse:
    conflicts = _extract_conflicts_from_report(
        error.extraction_report if isinstance(error.extraction_report, dict) else None
    )
    issues = [
        {
            "path": issue.path,
            "message": issue.message,
            "validator": issue.validator,
        }
        for issue in error.issues
    ]
    message = (
        "Encontramos valores diferentes nos quantitativos do projeto. "
        "A geração foi bloqueada para evitar um memorial incorreto."
    )
    request_id = get_request_id(request)
    details = {
        "issues": issues,
        "conflicts": conflicts,
        "extraction_report": error.extraction_report,
    }
    content: dict[str, Any] = {
        "detail": message,
        "errors": issues,
        "conflicts": conflicts,
        "error": {
            "code": "quantitative_conflict_unresolved",
            "message": message,
            "details": details,
        },
        "extraction_report": error.extraction_report,
    }
    if request_id is not None:
        content["error"]["request_id"] = request_id
    response = JSONResponse(status_code=409, content=content)
    if request_id is not None:
        response.headers["X-Request-ID"] = request_id
    return response


def _validation_detail_for_type(memorial_type: str) -> str:
    if memorial_type == "eletrico":
        return "Payload invalido para o memorial eletrico v1."
    if memorial_type == "telecom":
        return "Payload invalido para o memorial telecom v1."
    if memorial_type == "gas-natural":
        return "Payload invalido para o memorial gas natural v1."
    if memorial_type == "glp_v2":
        return "Payload invalido para o memorial GLP v2."
    return "Payload invalido para o memorial GLP v1."


def _log_validation_failure(
    request: Request,
    memorial_type: str,
    error: MemorialValidationError,
    event: str,
) -> None:
    issues = [
        {
            "path": issue.path,
            "message": issue.message,
            "validator": issue.validator,
        }
        for issue in error.issues
    ]

    extraction_report_summary: dict[str, Any] | None = None
    if isinstance(error.extraction_report, dict):
        extraction_report_summary = {
            "filled_count": len(error.extraction_report.get("filled", [])),
            "missing_count": len(error.extraction_report.get("missing", [])),
            "pending_count": len(error.extraction_report.get("pending", [])),
        }
        conflicts = error.extraction_report.get("conflicts")
        if isinstance(conflicts, list) and conflicts:
            extraction_report_summary["conflict_count"] = len(conflicts)

    logger.warning(
        "%s method=%s path=%s request_id=%s memorial_type=%s issues=%s extraction_report=%s",
        event,
        request.method,
        request.url.path,
        get_request_id(request),
        memorial_type,
        json.dumps(issues, ensure_ascii=False),
        json.dumps(extraction_report_summary, ensure_ascii=False)
        if extraction_report_summary is not None
        else "null",
    )


@router.get(
    "/api/v1/memoriais",
    response_model=GeneratedMemorialListResponse,
)
def list_persisted_memorials(
    request: Request,
    type: str | None = None,
    current_user: CurrentUser = Depends(require_user),
):
    if type is not None and type not in _SUPPORTED_MEMORIAL_LIST_TYPES:
        return _unsupported_memorial_type_response(type, request=request)
    return GeneratedMemorialListResponse(
        memorials=list_generated_memorials(type)
    )


@router.get(
    "/api/v1/memoriais/{memorial_id}",
    response_model=GeneratedMemorialResponse,
)
def get_persisted_memorial(
    memorial_id: str,
    request: Request,
    include_context: bool = False,
    current_user: CurrentUser = Depends(require_user),
):
    memorial = get_generated_memorial(
        memorial_id,
        include_context=include_context,
    )
    if memorial is None:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="generated_memorial_not_found",
            message="Memorial não encontrado.",
        )
    return memorial


@router.post(
    "/api/v1/memoriais/{memorial_id}/correcoes",
    response_model=GeneratedMemorialResponse,
    status_code=201,
)
def correct_persisted_memorial(
    memorial_id: str,
    payload: MemorialCorrectionsPayload,
    request: Request,
    current_user: CurrentUser = Depends(require_user),
):
    record = get_generated_memorial_record(
        memorial_id,
    )
    if record is None:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="generated_memorial_not_found",
            message="Memorial não encontrado.",
        )

    memorial_type = str(record.get("type") or "")
    if memorial_type not in _SUPPORTED_MEMORIAL_LIST_TYPES:
        return _unsupported_memorial_type_response(memorial_type, request=request)

    final_context = record.get("final_context")
    if not isinstance(final_context, dict):
        return build_error_response(
            status_code=409,
            code="generated_memorial_context_missing",
            message=(
                "Este memorial não possui contexto salvo para correção. "
                "Gere novamente para habilitar revisão pelo dashboard."
            ),
            request_id=get_request_id(request),
        )
    if not payload.corrections:
        return build_client_error_response(
            request=request,
            status_code=400,
            code="empty_corrections",
            message="Envie ao menos uma correção para gerar uma nova versão.",
        )

    corrected_context = merge_context(final_context, payload.corrections)
    corrected_report = _report_with_user_corrections(
        record.get("extraction_report"),
        payload.corrections,
    )

    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    rendered_output_path = output_path
    try:
        pipeline_result = _generate_memorial_from_context(
            memorial_type,
            corrected_context,
            output_path,
        )
        rendered_output_path = getattr(pipeline_result, "output_path", output_path)
        generated_context = getattr(pipeline_result, "context", corrected_context)
        return create_generated_memorial(
            memorial_type=memorial_type,
            owner_user_id=current_user.user_id,
            created_by_name=current_user.display_name,
            project_name=record.get("project_name") or _PROJECT_NAME_BY_TYPE[memorial_type],
            output_path=rendered_output_path,
            pdf_filenames=record.get("pdf_filenames") or [],
            observations=record.get("observations"),
            final_context=generated_context,
            extraction_report=corrected_report,
            conflicts=_extract_conflicts_from_report(corrected_report),
            context_version=record.get("context_version")
            or _CONTEXT_VERSION_BY_TYPE.get(memorial_type),
            template_version=record.get("template_version")
            or _TEMPLATE_VERSION_BY_TYPE.get(memorial_type),
        )
    except MemorialValidationError as error:
        _log_validation_failure(
            request,
            memorial_type,
            error,
            "Generated memorial correction validation failed",
        )
        return _validation_error_response(
            error, _validation_detail_for_type(memorial_type), request=request
        )
    except MemorialRenderError as error:
        logger.error(
            "Generated memorial correction render failed method=%s path=%s request_id=%s memorial_id=%s memorial_type=%s error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            memorial_id,
            memorial_type,
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)
    except GeneratedMemorialStorageError as error:
        logger.error(
            "Generated memorial correction persistence failed method=%s path=%s request_id=%s memorial_id=%s memorial_type=%s error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            memorial_id,
            memorial_type,
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_error_response(
            status_code=503,
            code="generated_memorial_storage_error",
            message="Armazenamento do memorial indisponível.",
            request_id=get_request_id(request),
        )
    finally:
        _remove_file(output_path)
        if rendered_output_path != output_path:
            _remove_file(rendered_output_path)


@router.get(
    "/api/v1/memoriais/{memorial_id}/download",
    response_model=GeneratedMemorialDownloadResponse,
)
def get_persisted_memorial_download(
    memorial_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_user),
):
    record = get_generated_memorial_record(
        memorial_id,
        owner_user_id=current_user.user_id,
    )
    if record is None:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="generated_memorial_not_found",
            message="Memorial não encontrado.",
        )
    if record.get("status") != "ready":
        return build_error_response(
            status_code=409,
            code="generated_memorial_not_ready",
            message="Memorial ainda não está disponível para download.",
            request_id=get_request_id(request),
        )
    try:
        return GeneratedMemorialDownloadResponse(
            download_url=create_signed_download_url(record)
        )
    except GeneratedMemorialArtifactNotFoundError:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="generated_memorial_artifact_missing",
            message="Arquivo do memorial não está mais disponível.",
        )
    except GeneratedMemorialStorageError as error:
        logger.error(
            "Generated memorial download failed method=%s path=%s request_id=%s memorial_id=%s error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            memorial_id,
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_error_response(
            status_code=503,
            code="generated_memorial_storage_error",
            message="Armazenamento do memorial indisponível.",
            request_id=get_request_id(request),
        )


@router.delete(
    "/api/v1/memoriais/{memorial_id}",
    status_code=204,
)
def delete_persisted_memorial(
    memorial_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_user),
):
    try:
        deleted = delete_generated_memorial(
            memorial_id,
            owner_user_id=current_user.user_id,
        )
    except GeneratedMemorialArtifactNotFoundError:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="generated_memorial_artifact_missing",
            message="Arquivo do memorial não está mais disponível.",
        )
    except GeneratedMemorialStorageError as error:
        logger.error(
            "Generated memorial delete failed method=%s path=%s request_id=%s memorial_id=%s error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            memorial_id,
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_error_response(
            status_code=503,
            code="generated_memorial_storage_error",
            message="Armazenamento do memorial indisponível.",
            request_id=get_request_id(request),
        )

    if not deleted:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="generated_memorial_not_found",
            message="Memorial não encontrado.",
        )
    return Response(status_code=204)


@router.post(
    "/api/v1/memoriais/{memorial_type}/from-files/persist",
    response_model=GeneratedMemorialResponse,
    status_code=201,
)
async def create_persisted_memorial_from_files(
    memorial_type: str,
    request: Request,
    files: list[UploadFile] | None = File(default=None),
    observations: str | None = Form(default=None),
    current_user: CurrentUser = Depends(require_user),
):
    if memorial_type not in _SUPPORTED_MEMORIAL_TYPES:
        return _unsupported_memorial_type_response(memorial_type, request=request)

    uploaded_files = files or []
    pdf_filenames = [file.filename for file in uploaded_files if file.filename]

    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        pipeline_result = await _generate_memorial_from_uploaded_files(
            memorial_type, uploaded_files, output_path
        )
        final_context: dict[str, Any] | None = None
        extraction_report_payload: dict[str, Any] | None = None
        if pipeline_result is not None:
            final_context = getattr(pipeline_result, "context", None)
            extraction_report_payload = _extraction_report_to_jsonable(
                getattr(pipeline_result, "extraction_report", None)
            )
        return create_generated_memorial(
            memorial_type=memorial_type,
            owner_user_id=current_user.user_id,
            created_by_name=current_user.display_name,
            project_name=_PROJECT_NAME_BY_TYPE[memorial_type],
            output_path=output_path,
            pdf_filenames=pdf_filenames,
            observations=observations,
            final_context=final_context,
            extraction_report=extraction_report_payload,
            conflicts=_extract_conflicts_from_report(extraction_report_payload),
            context_version=_CONTEXT_VERSION_BY_TYPE.get(memorial_type),
            template_version=_TEMPLATE_VERSION_BY_TYPE.get(memorial_type),
        )
    except MemorialValidationError as error:
        _log_validation_failure(
            request,
            memorial_type,
            error,
            "Generated memorial validation failed",
        )
        return _validation_error_response(
            error, _validation_detail_for_type(memorial_type), request=request
        )
    except (FileIngestionError, ProjectExtractionError) as error:
        logger.warning(
            "Generated memorial client error method=%s path=%s request_id=%s memorial_type=%s error_type=%s",
            request.method,
            request.url.path,
            get_request_id(request),
            memorial_type,
            type(error).__name__,
        )
        error_code = getattr(error, "code", None) or (
            "ingestion_error"
            if isinstance(error, FileIngestionError)
            else "project_extraction_error"
        )
        status_code = (
            _ingestion_error_status_code(error)
            if isinstance(error, FileIngestionError)
            else 400
        )
        return build_client_error_response(
            request=request,
            status_code=status_code,
            code=error_code,
            message=str(getattr(error, "detail", error)),
        )
    except MemorialRenderError as error:
        logger.error(
            "Generated memorial render failed method=%s path=%s request_id=%s memorial_type=%s error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            memorial_type,
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)
    except GeneratedMemorialStorageError as error:
        logger.error(
            "Generated memorial persistence failed method=%s path=%s request_id=%s memorial_type=%s error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            memorial_type,
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_error_response(
            status_code=503,
            code="generated_memorial_storage_error",
            message="Armazenamento do memorial indisponível.",
            request_id=get_request_id(request),
        )
    finally:
        _remove_file(output_path)


@router.post("/api/v1/memoriais/eletrico", dependencies=[Depends(require_user)])
def create_memorial_eletrico(
    payload: dict[str, Any],
    request: Request,
    background_tasks: BackgroundTasks,
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        generate_memorial_eletrico_v1(payload, output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(
            error, "Payload invalido para o memorial eletrico v1.", request=request
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        logger.error(
            "Memorial render failed method=%s path=%s request_id=%s memorial_type=eletrico error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)

    return _docx_file_response(
        output_path, background_tasks, "memorial_eletrico_v1.docx"
    )


@router.post("/api/v1/memoriais/telecom", dependencies=[Depends(require_user)])
def create_memorial_telecom(
    payload: dict[str, Any],
    request: Request,
    background_tasks: BackgroundTasks,
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        generate_memorial_telecom_v1(payload, output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(
            error, "Payload invalido para o memorial telecom v1.", request=request
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        logger.error(
            "Memorial render failed method=%s path=%s request_id=%s memorial_type=telecom error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)

    return _docx_file_response(
        output_path, background_tasks, "memorial_telecom_v1.docx"
    )


@router.post("/api/v1/memoriais/gas-natural", dependencies=[Depends(require_user)])
def create_memorial_gas_natural(
    payload: dict[str, Any],
    request: Request,
    background_tasks: BackgroundTasks,
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        generate_memorial_gas_natural_v1(payload, output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        _log_validation_failure(
            request,
            "gas-natural",
            error,
            "Memorial render validation failed",
        )
        return _validation_error_response(
            error, "Payload invalido para o memorial gas natural v1.", request=request
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        logger.error(
            "Memorial render failed method=%s path=%s request_id=%s memorial_type=gas-natural error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)

    return _docx_file_response(
        output_path, background_tasks, "memorial_gas_natural_v1.docx"
    )


@router.post("/api/v1/memoriais/glp", dependencies=[Depends(require_user)])
def create_memorial_glp(
    payload: dict[str, Any],
    request: Request,
    background_tasks: BackgroundTasks,
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        generate_memorial_glp_v1(payload, output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        _log_validation_failure(
            request,
            "glp",
            error,
            "Memorial render validation failed",
        )
        return _validation_error_response(
            error, "Payload invalido para o memorial GLP v1.", request=request
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        logger.error(
            "Memorial render failed method=%s path=%s request_id=%s memorial_type=glp error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)

    return _docx_file_response(output_path, background_tasks, "memorial_glp_v1.docx")


@router.post(
    "/api/v1/memoriais/eletrico/upload",
    response_model=FileIngestionResponse,
    dependencies=[Depends(require_user)],
)
async def upload_memorial_eletrico_files(
    request: Request,
    files: list[UploadFile] | None = File(default=None),
):
    result = None
    try:
        result = await ingest_uploaded_files(files or [])
    except FileIngestionError as error:
        return build_client_error_response(
            request=request,
            status_code=_ingestion_error_status_code(error),
            code=getattr(error, "code", None) or "ingestion_error",
            message=error.detail,
        )
    finally:
        if result is not None:
            cleanup_ingestion_result(result)

    return _file_ingestion_response(result)


@router.post(
    "/api/v1/memoriais/telecom/upload",
    response_model=FileIngestionResponse,
    dependencies=[Depends(require_user)],
)
async def upload_memorial_telecom_files(
    request: Request,
    files: list[UploadFile] | None = File(default=None),
):
    result = None
    try:
        result = await ingest_uploaded_files(files or [])
    except FileIngestionError as error:
        return build_client_error_response(
            request=request,
            status_code=_ingestion_error_status_code(error),
            code=getattr(error, "code", None) or "ingestion_error",
            message=error.detail,
        )
    finally:
        if result is not None:
            cleanup_ingestion_result(result)

    return _file_ingestion_response(result)


@router.post(
    "/api/v1/memoriais/gas-natural/upload",
    response_model=FileIngestionResponse,
    dependencies=[Depends(require_user)],
)
async def upload_memorial_gas_natural_files(
    request: Request,
    files: list[UploadFile] | None = File(default=None),
):
    result = None
    try:
        result = await ingest_uploaded_files(files or [])
    except FileIngestionError as error:
        return build_client_error_response(
            request=request,
            status_code=_ingestion_error_status_code(error),
            code=getattr(error, "code", None) or "ingestion_error",
            message=error.detail,
        )
    finally:
        if result is not None:
            cleanup_ingestion_result(result)

    return _file_ingestion_response(result)


def _process_review_session(
    session_id: str, owner_user_id: str, ingestion_result: FileIngestionResult
) -> None:
    """Background task: extracts context from ingested files and updates session."""
    from dataclasses import asdict

    try:
        mapping, report = extract_mapping_from_ingested_files(ingestion_result.files)
        update_session(
            session_id,
            owner_user_id,
            status=STATUS_PENDING_REVIEW,
            partial_context=mapping.context,
            extraction_report=asdict(report),
        )
        logger.info(
            "Session %s extraction complete: status=%s",
            session_id,
            STATUS_PENDING_REVIEW,
        )
    except Exception as error:
        logger.error(
            "Session extraction failed session_id=%s error_type=%s\n%s",
            session_id,
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        update_session(session_id, owner_user_id, status=STATUS_FAILED, error=str(error))
    finally:
        cleanup_ingestion_result(ingestion_result)


@router.post("/api/v1/memoriais/eletrico/from-files", dependencies=[Depends(require_user)])
async def create_memorial_eletrico_from_files(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        await generate_memorial_eletrico_v1_from_uploaded_files(
            files or [], output_path
        )
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(
            error, "Payload invalido para o memorial eletrico v1.", request=request
        )
    except (FileIngestionError, ProjectExtractionError) as error:
        _remove_file(output_path)
        error_code = getattr(error, "code", None) or (
            "ingestion_error"
            if isinstance(error, FileIngestionError)
            else "project_extraction_error"
        )
        status_code = (
            _ingestion_error_status_code(error)
            if isinstance(error, FileIngestionError)
            else 400
        )
        return build_client_error_response(
            request=request,
            status_code=status_code,
            code=error_code,
            message=str(getattr(error, "detail", error)),
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        logger.error(
            "Memorial render from files failed method=%s path=%s request_id=%s memorial_type=eletrico error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)

    return _docx_file_response(
        output_path, background_tasks, "memorial_eletrico_v1.docx"
    )


@router.post("/api/v1/memoriais/telecom/from-files", dependencies=[Depends(require_user)])
async def create_memorial_telecom_from_files(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        await generate_memorial_telecom_v1_from_uploaded_files(files or [], output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(
            error, "Payload invalido para o memorial telecom v1.", request=request
        )
    except (FileIngestionError, ProjectExtractionError) as error:
        _remove_file(output_path)
        error_code = getattr(error, "code", None) or (
            "ingestion_error"
            if isinstance(error, FileIngestionError)
            else "project_extraction_error"
        )
        status_code = (
            _ingestion_error_status_code(error)
            if isinstance(error, FileIngestionError)
            else 400
        )
        return build_client_error_response(
            request=request,
            status_code=status_code,
            code=error_code,
            message=str(getattr(error, "detail", error)),
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        logger.error(
            "Memorial render from files failed method=%s path=%s request_id=%s memorial_type=telecom error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)

    return _docx_file_response(
        output_path, background_tasks, "memorial_telecom_v1.docx"
    )


@router.post("/api/v1/memoriais/gas-natural/from-files", dependencies=[Depends(require_user)])
async def create_memorial_gas_natural_from_files(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        await generate_memorial_gas_natural_v1_from_uploaded_files(
            files or [], output_path
        )
    except MemorialValidationError as error:
        _remove_file(output_path)
        _log_validation_failure(
            request,
            "gas-natural",
            error,
            "Memorial render from files validation failed",
        )
        return _validation_error_response(
            error, "Payload invalido para o memorial gas natural v1.", request=request
        )
    except (FileIngestionError, ProjectExtractionError) as error:
        _remove_file(output_path)
        error_code = getattr(error, "code", None) or (
            "ingestion_error"
            if isinstance(error, FileIngestionError)
            else "project_extraction_error"
        )
        status_code = (
            _ingestion_error_status_code(error)
            if isinstance(error, FileIngestionError)
            else 400
        )
        return build_client_error_response(
            request=request,
            status_code=status_code,
            code=error_code,
            message=str(getattr(error, "detail", error)),
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        logger.error(
            "Memorial render from files failed method=%s path=%s request_id=%s memorial_type=gas-natural error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)

    return _docx_file_response(
        output_path, background_tasks, "memorial_gas_natural_v1.docx"
    )


@router.post(
    "/api/v1/memoriais/glp/upload",
    response_model=FileIngestionResponse,
    dependencies=[Depends(require_user)],
)
async def upload_memorial_glp_files(
    request: Request,
    files: list[UploadFile] | None = File(default=None),
):
    result = None
    try:
        result = await ingest_uploaded_files(files or [])
    except FileIngestionError as error:
        return build_client_error_response(
            request=request,
            status_code=_ingestion_error_status_code(error),
            code=getattr(error, "code", None) or "ingestion_error",
            message=error.detail,
        )
    finally:
        if result is not None:
            cleanup_ingestion_result(result)

    return _file_ingestion_response(result)


@router.post("/api/v1/memoriais/glp/from-files", dependencies=[Depends(require_user)])
async def create_memorial_glp_from_files(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        await generate_memorial_glp_v1_from_uploaded_files(files or [], output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(
            error, "Payload invalido para o memorial GLP v1.", request=request
        )
    except (FileIngestionError, ProjectExtractionError) as error:
        _remove_file(output_path)
        error_code = getattr(error, "code", None) or (
            "ingestion_error"
            if isinstance(error, FileIngestionError)
            else "project_extraction_error"
        )
        status_code = (
            _ingestion_error_status_code(error)
            if isinstance(error, FileIngestionError)
            else 400
        )
        return build_client_error_response(
            request=request,
            status_code=status_code,
            code=error_code,
            message=str(getattr(error, "detail", error)),
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        logger.error(
            "Memorial render from files failed method=%s path=%s request_id=%s memorial_type=glp error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)

    return _docx_file_response(output_path, background_tasks, "memorial_glp_v1.docx")


def _glp_v2_route_guard(request: Request) -> JSONResponse | None:
    if not GLP_V2_TEMPLATE_PATH.is_file():
        return build_client_error_response(
            request=request,
            status_code=503,
            code="glp_v2_template_pending",
            message=(
                "GLP v2 template DOCX must be authored manually before this route can serve documents."
            ),
        )
    return None


@router.post("/api/v1/memoriais/glp/v2/from-files", dependencies=[Depends(require_user)])
async def create_memorial_glp_v2_from_files(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
):
    blocked = _glp_v2_route_guard(request)
    if blocked is not None:
        return blocked

    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        await generate_memorial_glp_v2_from_uploaded_files(files or [], output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(
            error, "Payload invalido para o memorial GLP v2.", request=request
        )
    except (FileIngestionError, ProjectExtractionError) as error:
        _remove_file(output_path)
        error_code = getattr(error, "code", None) or (
            "ingestion_error"
            if isinstance(error, FileIngestionError)
            else "project_extraction_error"
        )
        status_code = (
            _ingestion_error_status_code(error)
            if isinstance(error, FileIngestionError)
            else 400
        )
        return build_client_error_response(
            request=request,
            status_code=status_code,
            code=error_code,
            message=str(getattr(error, "detail", error)),
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        logger.error(
            "Memorial render from files failed method=%s path=%s request_id=%s memorial_type=glp_v2 error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)

    return _docx_file_response(output_path, background_tasks, "memorial_glp_v2.docx")


@router.post(
    "/api/v1/memoriais/glp/v2/from-files/persist",
    response_model=GeneratedMemorialResponse,
    status_code=201,
)
async def create_persisted_memorial_glp_v2_from_files(
    request: Request,
    files: list[UploadFile] | None = File(default=None),
    observations: str | None = Form(default=None),
    current_user: CurrentUser = Depends(require_user),
):
    blocked = _glp_v2_route_guard(request)
    if blocked is not None:
        return blocked

    uploaded_files = files or []
    pdf_filenames = [file.filename for file in uploaded_files if file.filename]

    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        pipeline_result = await generate_memorial_glp_v2_from_uploaded_files(
            uploaded_files,
            output_path,
        )
        final_context: dict[str, Any] | None = getattr(pipeline_result, "context", None)
        extraction_report_payload = _extraction_report_to_jsonable(
            getattr(pipeline_result, "extraction_report", None)
        )
        return create_generated_memorial(
            memorial_type="glp_v2",
            owner_user_id=current_user.user_id,
            created_by_name=current_user.display_name,
            project_name="Memorial GLP v2",
            output_path=output_path,
            pdf_filenames=pdf_filenames,
            observations=observations,
            final_context=final_context,
            extraction_report=extraction_report_payload,
            conflicts=_extract_conflicts_from_report(extraction_report_payload),
            context_version="glp_v2",
            template_version="glp_v2",
        )
    except MemorialValidationError as error:
        _log_validation_failure(
            request,
            "glp_v2",
            error,
            "Generated memorial GLP v2 validation failed",
        )
        return _validation_error_response(
            error, "Payload invalido para o memorial GLP v2.", request=request
        )
    except (FileIngestionError, ProjectExtractionError) as error:
        logger.warning(
            "Generated memorial client error method=%s path=%s request_id=%s memorial_type=glp_v2 error_type=%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
        )
        error_code = getattr(error, "code", None) or (
            "ingestion_error"
            if isinstance(error, FileIngestionError)
            else "project_extraction_error"
        )
        status_code = (
            _ingestion_error_status_code(error)
            if isinstance(error, FileIngestionError)
            else 400
        )
        return build_client_error_response(
            request=request,
            status_code=status_code,
            code=error_code,
            message=str(getattr(error, "detail", error)),
        )
    except MemorialRenderError as error:
        logger.error(
            "Generated memorial render failed method=%s path=%s request_id=%s memorial_type=glp_v2 error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)
    except GeneratedMemorialStorageError as error:
        logger.error(
            "Generated memorial persistence failed method=%s path=%s request_id=%s memorial_type=glp_v2 error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_error_response(
            status_code=503,
            code="generated_memorial_storage_error",
            message="Armazenamento do memorial indisponível.",
            request_id=get_request_id(request),
        )
    finally:
        _remove_file(output_path)


# ── Fluxo de revisão manual ──────────────────────────────────────────────────


@router.post(
    "/api/v1/memoriais/eletrico/sessoes",
    response_model=SessionCreatedResponse,
    status_code=202,
)
async def create_review_session(
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
    current_user: CurrentUser = Depends(require_user),
):
    try:
        ingestion_result = await ingest_uploaded_files(files or [])
    except FileIngestionError as error:
        return build_client_error_response(
            request=request,
            status_code=_ingestion_error_status_code(error),
            code=getattr(error, "code", None) or "ingestion_error",
            message=error.detail,
        )

    session_id: str | None = None
    try:
        session_id = create_session(current_user.user_id)
        logger.info("Review session created: session_id=%s", session_id)
        background_tasks.add_task(
            _process_review_session,
            session_id,
            current_user.user_id,
            ingestion_result,
        )
    except Exception:
        cleanup_ingestion_result(ingestion_result)
        if session_id is not None:
            delete_session(session_id)
        raise

    return SessionCreatedResponse(session_id=session_id, status="processing")


@router.get(
    "/api/v1/memoriais/eletrico/sessoes/{session_id}",
    response_model=SessionStateResponse,
)
def get_review_session(
    session_id: str,
    request: Request,
    current_user: CurrentUser = Depends(require_user),
):
    session = load_session(session_id, current_user.user_id)
    if session is None:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="review_session_not_found",
            message="Sessão não encontrada.",
        )
    return SessionStateResponse(**session.__dict__)


@router.patch(
    "/api/v1/memoriais/eletrico/sessoes/{session_id}/contexto",
    response_model=SessionStateResponse,
)
def patch_review_session_context(
    session_id: str,
    payload: ContextCorrectionsPayload,
    request: Request,
    current_user: CurrentUser = Depends(require_user),
):
    session = load_session(session_id, current_user.user_id)
    if session is None:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="review_session_not_found",
            message="Sessão não encontrada.",
        )
    if session.status == "processing":
        return build_client_error_response(
            request=request,
            status_code=409,
            code="review_session_processing",
            message="Extração ainda em andamento.",
        )

    merged_corrections = merge_context(session.corrections, payload.corrections)
    updated = update_session(
        session_id,
        current_user.user_id,
        corrections=merged_corrections,
    )
    return SessionStateResponse(**updated.__dict__)


@router.post("/api/v1/memoriais/eletrico/sessoes/{session_id}/gerar")
def generate_from_review_session(
    session_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_user),
):
    session = load_session(session_id, current_user.user_id)
    if session is None:
        return build_client_error_response(
            request=request,
            status_code=404,
            code="review_session_not_found",
            message="Sessão não encontrada.",
        )
    if session.status not in (STATUS_PENDING_REVIEW, "completed"):
        return build_client_error_response(
            request=request,
            status_code=409,
            code="review_session_not_ready",
            message=f"Sessão em status '{session.status}' não pode gerar memorial.",
            details={"session_status": session.status},
        )

    merged = merge_context(session.partial_context, session.corrections)

    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        generate_memorial_eletrico_v1(merged, output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(
            error, "Payload invalido para o memorial eletrico v1.", request=request
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        logger.error(
            "Reviewed memorial render failed method=%s path=%s request_id=%s session_id=%s error_type=%s\n%s",
            request.method,
            request.url.path,
            get_request_id(request),
            session_id,
            type(error).__name__,
            format_sanitized_exception_trace(error),
        )
        return build_internal_server_error_response(request)

    background_tasks.add_task(delete_session, session_id)
    return _docx_file_response(
        output_path, background_tasks, "memorial_eletrico_v1.docx"
    )
