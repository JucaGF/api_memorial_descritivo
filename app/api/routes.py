from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

from app.services.memorial_renderer import MemorialRenderError
from app.services.memorial_validator import MemorialValidationError
from app.services.pipeline import generate_memorial_eletrico_v1


DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

router = APIRouter()


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


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
    except MemorialRenderError as error:
        _remove_file(output_path)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Falha ao renderizar o memorial eletrico v1.",
                "error": str(error),
            },
        )

    background_tasks.add_task(_remove_file, output_path)
    return FileResponse(
        path=output_path,
        media_type=DOCX_MEDIA_TYPE,
        filename="memorial_eletrico_v1.docx",
    )
