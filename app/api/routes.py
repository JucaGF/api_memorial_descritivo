from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.schemas.file_ingestion import FileIngestionResponse
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
from app.services.pipeline import generate_memorial_eletrico_v1
from app.services.pipeline_from_files import (
    extract_mapping_from_ingested_files,
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


DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

router = APIRouter()


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _validation_error_response(error: MemorialValidationError) -> JSONResponse:
    content: dict = {
        "detail": "Payload invalido para o memorial eletrico v1.",
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
) -> FileResponse:
    background_tasks.add_task(_remove_file, output_path)
    return FileResponse(
        path=output_path,
        media_type=DOCX_MEDIA_TYPE,
        filename="memorial_eletrico_v1.docx",
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
        return _validation_error_response(error)
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Falha ao renderizar o memorial eletrico v1.",
                "error": str(error),
            },
        )

    return _docx_file_response(output_path, background_tasks)


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
    except Exception as error:
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
        return _validation_error_response(error)
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

    return _docx_file_response(output_path, background_tasks)


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

    session_id = create_session()
    background_tasks.add_task(_process_review_session, session_id, ingestion_result)
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
        return _validation_error_response(error)
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Falha ao renderizar o memorial.", "error": str(error)},
        )

    background_tasks.add_task(delete_session, session_id)
    return _docx_file_response(output_path, background_tasks)
