from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from tempfile import mkdtemp

from fastapi import UploadFile


ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_CONTENT_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
}


@dataclass(frozen=True)
class IngestedFileMetadata:
    original_filename: str
    stored_filename: str
    content_type: str
    extension: str
    size_bytes: int
    saved_path: str


@dataclass(frozen=True)
class FileIngestionResult:
    request_dir: str
    files: list[IngestedFileMetadata]


class FileIngestionError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def cleanup_ingestion_result(result: FileIngestionResult | None) -> None:
    if result is None:
        return
    shutil.rmtree(result.request_dir, ignore_errors=True)


def _safe_filename_stem(filename: str) -> str:
    stem = Path(filename).stem.lower()
    sanitized = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return sanitized or "arquivo"


def _validate_upload(upload: UploadFile) -> tuple[str, str]:
    if not upload.filename:
        raise FileIngestionError("Todos os arquivos enviados precisam ter nome.")

    extension = Path(upload.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise FileIngestionError(
            f"Extensao nao suportada para upload: {upload.filename}."
        )

    content_type = upload.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES[extension]:
        raise FileIngestionError(
            f"Content-Type invalido para o arquivo {upload.filename}: {content_type}."
        )

    return extension, content_type


async def ingest_uploaded_files(files: list[UploadFile]) -> FileIngestionResult:
    if not files:
        raise FileIngestionError("Envie ao menos um arquivo PDF ou DOCX.")

    request_dir = Path(mkdtemp(prefix="eletrico_v1_upload_"))
    saved_files: list[IngestedFileMetadata] = []
    result: FileIngestionResult | None = None

    try:
        for index, upload in enumerate(files, start=1):
            try:
                extension, content_type = _validate_upload(upload)
                stored_filename = f"{index:02d}_{_safe_filename_stem(upload.filename)}{extension}"
                saved_path = request_dir / stored_filename

                size_bytes = 0
                with saved_path.open("wb") as output_file:
                    while True:
                        chunk = await upload.read(1024 * 1024)
                        if not chunk:
                            break
                        output_file.write(chunk)
                        size_bytes += len(chunk)
            finally:
                await upload.close()

            saved_files.append(
                IngestedFileMetadata(
                    original_filename=upload.filename,
                    stored_filename=stored_filename,
                    content_type=content_type,
                    extension=extension,
                    size_bytes=size_bytes,
                    saved_path=str(saved_path),
                )
            )

        result = FileIngestionResult(
            request_dir=str(request_dir),
            files=saved_files,
        )
        return result
    except Exception:
        cleanup_ingestion_result(
            FileIngestionResult(
                request_dir=str(request_dir),
                files=saved_files,
            )
        )
        raise
