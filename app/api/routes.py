from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.schemas.file_ingestion import FileIngestionResponse
from app.services.file_ingestion import (
    FileIngestionError,
    cleanup_ingestion_result,
    ingest_uploaded_files,
)
from app.services.memorial_renderer import MemorialRenderError
from app.services.memorial_validator import MemorialValidationError
from app.services.pipeline import generate_memorial_eletrico_v1
from app.services.pipeline_from_files import (
    generate_memorial_eletrico_v1_from_uploaded_files,
)
from app.services.project_extractor import ProjectExtractionError


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
    return JSONResponse(
        status_code=400,
        content={
            "detail": "Payload invalido para o memorial eletrico v1.",
            "errors": [
                {
                    "path": issue.path,
                    "message": issue.message,
                    "validator": issue.validator,
                }
                for issue in error.issues
            ],
        },
    )


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
