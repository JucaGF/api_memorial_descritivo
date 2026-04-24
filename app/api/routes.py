from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from app.schemas.file_ingestion import FileIngestionResponse
from app.schemas.generated_memorial import (
    GeneratedMemorialDownloadResponse,
    GeneratedMemorialListResponse,
    GeneratedMemorialResponse,
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
    cleanup_ingestion_result,
    ingest_uploaded_files,
)
from app.services.memorial_renderer import MemorialRenderError
from app.services.memorial_validator import MemorialValidationError
from app.services.generated_memorial_store import (
    create_generated_memorial,
    delete_generated_memorial,
    create_signed_download_url,
    get_generated_memorial,
    get_generated_memorial_record,
    list_generated_memorials,
)
from app.services.pipeline import (
    generate_memorial_eletrico_v1,
    generate_memorial_gas_natural_v1,
    generate_memorial_glp_v1,
    generate_memorial_telecom_v1,
)
from app.services.pipeline_from_files import (
    extract_mapping_from_ingested_files,
    generate_memorial_gas_natural_v1_from_uploaded_files,
    generate_memorial_glp_v1_from_uploaded_files,
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

logger = logging.getLogger(__name__)

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

router = APIRouter()

_SUPPORTED_MEMORIAL_TYPES = {"eletrico", "telecom", "gas-natural", "glp"}
_PROJECT_NAME_BY_TYPE = {
    "eletrico": "Memorial Elétrico",
    "telecom": "Memorial Telecom",
    "gas-natural": "Memorial Gás Natural",
    "glp": "Memorial GLP",
}


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _validation_error_response(
    error: MemorialValidationError,
    detail: str,
) -> JSONResponse:
    content: dict = {
        "detail": detail,
        "errors": [
            {
                "path": issue.path,
                "message": issue.message,
                "validator": issue.validator,
            }
            for issue in error.issues
        ],
    }
    if error.extraction_report is not None:
        content["extraction_report"] = error.extraction_report
    return JSONResponse(status_code=400, content=content)


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


def _unsupported_memorial_type_response(memorial_type: str) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"detail": f"Tipo de memorial não encontrado: {memorial_type}."},
    )


async def _generate_memorial_from_uploaded_files(
    memorial_type: str,
    files: list[UploadFile],
    output_path: Path,
) -> None:
    if memorial_type == "eletrico":
        await generate_memorial_eletrico_v1_from_uploaded_files(files, output_path)
        return
    if memorial_type == "telecom":
        await generate_memorial_telecom_v1_from_uploaded_files(files, output_path)
        return
    if memorial_type == "gas-natural":
        await generate_memorial_gas_natural_v1_from_uploaded_files(files, output_path)
        return
    if memorial_type == "glp":
        await generate_memorial_glp_v1_from_uploaded_files(files, output_path)
        return
    raise ValueError(f"Tipo de memorial não suportado: {memorial_type}.")


def _validation_detail_for_type(memorial_type: str) -> str:
    if memorial_type == "eletrico":
        return "Payload invalido para o memorial eletrico v1."
    if memorial_type == "telecom":
        return "Payload invalido para o memorial telecom v1."
    if memorial_type == "gas-natural":
        return "Payload invalido para o memorial gas natural v1."
    return "Payload invalido para o memorial GLP v1."


@router.get(
    "/api/v1/memoriais",
    response_model=GeneratedMemorialListResponse,
)
def list_persisted_memorials(type: str | None = None):
    if type is not None and type not in _SUPPORTED_MEMORIAL_TYPES:
        return _unsupported_memorial_type_response(type)
    return GeneratedMemorialListResponse(memorials=list_generated_memorials(type))


@router.get(
    "/api/v1/memoriais/{memorial_id}",
    response_model=GeneratedMemorialResponse,
)
def get_persisted_memorial(memorial_id: str):
    memorial = get_generated_memorial(memorial_id)
    if memorial is None:
        return JSONResponse(status_code=404, content={"detail": "Memorial não encontrado."})
    return memorial


@router.get(
    "/api/v1/memoriais/{memorial_id}/download",
    response_model=GeneratedMemorialDownloadResponse,
)
def get_persisted_memorial_download(memorial_id: str):
    record = get_generated_memorial_record(memorial_id)
    if record is None:
        return JSONResponse(status_code=404, content={"detail": "Memorial não encontrado."})
    return GeneratedMemorialDownloadResponse(download_url=create_signed_download_url(record))


@router.delete(
    "/api/v1/memoriais/{memorial_id}",
    status_code=204,
)
def delete_persisted_memorial(memorial_id: str):
    if not delete_generated_memorial(memorial_id):
        return JSONResponse(status_code=404, content={"detail": "Memorial não encontrado."})
    return Response(status_code=204)


@router.post(
    "/api/v1/memoriais/{memorial_type}/from-files/persist",
    response_model=GeneratedMemorialResponse,
    status_code=201,
)
async def create_persisted_memorial_from_files(
    memorial_type: str,
    files: list[UploadFile] | None = File(default=None),
    observations: str | None = Form(default=None),
):
    import logging
    logging.warning(f"[DEBUG] memorial_type={memorial_type}, files={files}, observations={observations}")
    if files:
        for f in files:
            logging.warning(f"[DEBUG] file: filename={f.filename}, content_type={f.content_type}, size={f.size}")

    if memorial_type not in _SUPPORTED_MEMORIAL_TYPES:
        return _unsupported_memorial_type_response(memorial_type)

    uploaded_files = files or []
    pdf_filenames = [file.filename for file in uploaded_files if file.filename]

    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        await _generate_memorial_from_uploaded_files(memorial_type, uploaded_files, output_path)
        return create_generated_memorial(
            memorial_type=memorial_type,
            project_name=_PROJECT_NAME_BY_TYPE[memorial_type],
            output_path=output_path,
            pdf_filenames=pdf_filenames,
            observations=observations,
        )
    except MemorialValidationError as error:
        import traceback
        logging.warning(f"[DEBUG-ERR] MemorialValidationError: {error}\n{traceback.format_exc()}")
        return _validation_error_response(error, _validation_detail_for_type(memorial_type))
    except (FileIngestionError, ProjectExtractionError) as error:
        import traceback
        logging.warning(f"[DEBUG-ERR] {type(error).__name__}: {error}\n{traceback.format_exc()}")
        return JSONResponse(status_code=400, content={"detail": str(error)})
    except MemorialRenderError as error:
        return JSONResponse(
            status_code=500,
            content={"detail": "Falha ao renderizar o memorial.", "error": str(error)},
        )
    finally:
        _remove_file(output_path)


@router.post("/api/v1/memoriais/eletrico")
def create_memorial_eletrico(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        generate_memorial_eletrico_v1(payload, output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(error, "Payload invalido para o memorial eletrico v1.")
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Falha ao renderizar o memorial eletrico v1.",
                "error": str(error),
            },
        )

    return _docx_file_response(output_path, background_tasks, "memorial_eletrico_v1.docx")


@router.post("/api/v1/memoriais/telecom")
def create_memorial_telecom(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        generate_memorial_telecom_v1(payload, output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(error, "Payload invalido para o memorial telecom v1.")
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Falha ao renderizar o memorial telecom v1.",
                "error": str(error),
            },
        )

    return _docx_file_response(output_path, background_tasks, "memorial_telecom_v1.docx")


@router.post("/api/v1/memoriais/gas-natural")
def create_memorial_gas_natural(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        generate_memorial_gas_natural_v1(payload, output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(error, "Payload invalido para o memorial gas natural v1.")
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Falha ao renderizar o memorial gas natural v1.",
                "error": str(error),
            },
        )

    return _docx_file_response(output_path, background_tasks, "memorial_gas_natural_v1.docx")


@router.post("/api/v1/memoriais/glp")
def create_memorial_glp(
    payload: dict[str, Any],
    background_tasks: BackgroundTasks,
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        generate_memorial_glp_v1(payload, output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(error, "Payload invalido para o memorial GLP v1.")
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Falha ao renderizar o memorial GLP v1.",
                "error": str(error),
            },
        )

    return _docx_file_response(output_path, background_tasks, "memorial_glp_v1.docx")


@router.post(
    "/api/v1/memoriais/eletrico/upload",
    response_model=FileIngestionResponse,
)
async def upload_memorial_eletrico_files(
    files: list[UploadFile] | None = File(default=None),
):
    result = None
    try:
        result = await ingest_uploaded_files(files or [])
    except FileIngestionError as error:
        return JSONResponse(
            status_code=400,
            content={"detail": error.detail},
        )
    finally:
        if result is not None:
            cleanup_ingestion_result(result)

    return _file_ingestion_response(result)


@router.post(
    "/api/v1/memoriais/telecom/upload",
    response_model=FileIngestionResponse,
)
async def upload_memorial_telecom_files(
    files: list[UploadFile] | None = File(default=None),
):
    result = None
    try:
        result = await ingest_uploaded_files(files or [])
    except FileIngestionError as error:
        return JSONResponse(
            status_code=400,
            content={"detail": error.detail},
        )
    finally:
        if result is not None:
            cleanup_ingestion_result(result)

    return _file_ingestion_response(result)


@router.post(
    "/api/v1/memoriais/gas-natural/upload",
    response_model=FileIngestionResponse,
)
async def upload_memorial_gas_natural_files(
    files: list[UploadFile] | None = File(default=None),
):
    result = None
    try:
        result = await ingest_uploaded_files(files or [])
    except FileIngestionError as error:
        return JSONResponse(
            status_code=400,
            content={"detail": error.detail},
        )
    finally:
        if result is not None:
            cleanup_ingestion_result(result)

    return _file_ingestion_response(result)


def _process_review_session(session_id: str, ingestion_result: FileIngestionResult) -> None:
    """Background task: extracts context from ingested files and updates session."""
    from dataclasses import asdict

    try:
        mapping, report = extract_mapping_from_ingested_files(ingestion_result.files)
        update_session(
            session_id,
            status=STATUS_PENDING_REVIEW,
            partial_context=mapping.context,
            extraction_report=asdict(report),
        )
        logger.info("Session %s extraction complete: status=%s", session_id, STATUS_PENDING_REVIEW)
    except Exception as error:
        logger.error("Session %s extraction failed: %s", session_id, error)
        update_session(session_id, status=STATUS_FAILED, error=str(error))
    finally:
        cleanup_ingestion_result(ingestion_result)


@router.post("/api/v1/memoriais/eletrico/from-files")
async def create_memorial_eletrico_from_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        await generate_memorial_eletrico_v1_from_uploaded_files(files or [], output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(error, "Payload invalido para o memorial eletrico v1.")
    except (FileIngestionError, ProjectExtractionError) as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=400,
            content={"detail": str(error)},
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Falha ao renderizar o memorial eletrico v1.",
                "error": str(error),
            },
        )

    return _docx_file_response(output_path, background_tasks, "memorial_eletrico_v1.docx")


@router.post("/api/v1/memoriais/telecom/from-files")
async def create_memorial_telecom_from_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        await generate_memorial_telecom_v1_from_uploaded_files(files or [], output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(error, "Payload invalido para o memorial telecom v1.")
    except (FileIngestionError, ProjectExtractionError) as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=400,
            content={"detail": str(error)},
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Falha ao renderizar o memorial telecom v1.",
                "error": str(error),
            },
        )

    return _docx_file_response(output_path, background_tasks, "memorial_telecom_v1.docx")


@router.post("/api/v1/memoriais/gas-natural/from-files")
async def create_memorial_gas_natural_from_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        await generate_memorial_gas_natural_v1_from_uploaded_files(files or [], output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(error, "Payload invalido para o memorial gas natural v1.")
    except (FileIngestionError, ProjectExtractionError) as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=400,
            content={"detail": str(error)},
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Falha ao renderizar o memorial gas natural v1.",
                "error": str(error),
            },
        )

    return _docx_file_response(output_path, background_tasks, "memorial_gas_natural_v1.docx")


@router.post(
    "/api/v1/memoriais/glp/upload",
    response_model=FileIngestionResponse,
)
async def upload_memorial_glp_files(
    files: list[UploadFile] | None = File(default=None),
):
    result = None
    try:
        result = await ingest_uploaded_files(files or [])
    except FileIngestionError as error:
        return JSONResponse(
            status_code=400,
            content={"detail": error.detail},
        )
    finally:
        if result is not None:
            cleanup_ingestion_result(result)

    return _file_ingestion_response(result)


@router.post("/api/v1/memoriais/glp/from-files")
async def create_memorial_glp_from_files(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
):
    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        await generate_memorial_glp_v1_from_uploaded_files(files or [], output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(error, "Payload invalido para o memorial GLP v1.")
    except (FileIngestionError, ProjectExtractionError) as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=400,
            content={"detail": str(error)},
        )
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Falha ao renderizar o memorial GLP v1.",
                "error": str(error),
            },
        )

    return _docx_file_response(output_path, background_tasks, "memorial_glp_v1.docx")


# ── Fluxo de revisão manual ──────────────────────────────────────────────────

@router.post(
    "/api/v1/memoriais/eletrico/sessoes",
    response_model=SessionCreatedResponse,
    status_code=202,
)
async def create_review_session(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] | None = File(default=None),
):
    try:
        ingestion_result = await ingest_uploaded_files(files or [])
    except FileIngestionError as error:
        return JSONResponse(status_code=400, content={"detail": error.detail})

    session_id: str | None = None
    try:
        session_id = create_session()
        logger.info("Review session created: session_id=%s", session_id)
        background_tasks.add_task(_process_review_session, session_id, ingestion_result)
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
def get_review_session(session_id: str):
    session = load_session(session_id)
    if session is None:
        return JSONResponse(status_code=404, content={"detail": "Sessão não encontrada."})
    return SessionStateResponse(**session.__dict__)


@router.patch(
    "/api/v1/memoriais/eletrico/sessoes/{session_id}/contexto",
    response_model=SessionStateResponse,
)
def patch_review_session_context(session_id: str, payload: ContextCorrectionsPayload):
    session = load_session(session_id)
    if session is None:
        return JSONResponse(status_code=404, content={"detail": "Sessão não encontrada."})
    if session.status == "processing":
        return JSONResponse(status_code=409, content={"detail": "Extração ainda em andamento."})

    merged_corrections = merge_context(session.corrections, payload.corrections)
    updated = update_session(session_id, corrections=merged_corrections)
    return SessionStateResponse(**updated.__dict__)


@router.post("/api/v1/memoriais/eletrico/sessoes/{session_id}/gerar")
def generate_from_review_session(session_id: str, background_tasks: BackgroundTasks):
    session = load_session(session_id)
    if session is None:
        return JSONResponse(status_code=404, content={"detail": "Sessão não encontrada."})
    if session.status not in (STATUS_PENDING_REVIEW, "completed"):
        return JSONResponse(
            status_code=409,
            content={"detail": f"Sessão em status '{session.status}' não pode gerar memorial."},
        )

    merged = merge_context(session.partial_context, session.corrections)

    with NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        output_path = Path(temp_file.name)

    try:
        generate_memorial_eletrico_v1(merged, output_path)
    except MemorialValidationError as error:
        _remove_file(output_path)
        return _validation_error_response(error, "Payload invalido para o memorial eletrico v1.")
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Falha ao renderizar o memorial.", "error": str(error)},
        )

    background_tasks.add_task(delete_session, session_id)
    return _docx_file_response(output_path, background_tasks, "memorial_eletrico_v1.docx")
