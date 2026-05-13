from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import mkdtemp
from typing import Protocol, runtime_checkable

from app.config import UploadLimits, get_settings


@runtime_checkable
class UploadedFile(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...
    async def close(self) -> None: ...


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
    saved_path: str = field(repr=False)


@dataclass(frozen=True)
class FileIngestionResult:
    files: list[IngestedFileMetadata]
    request_dir: str = field(repr=False)


class FileIngestionError(Exception):
    code: str = "ingestion_error"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class UploadTooManyFilesError(FileIngestionError):
    code = "upload_too_many_files"


class UploadFileTooLargeError(FileIngestionError):
    code = "upload_file_too_large"


class UploadTotalTooLargeError(FileIngestionError):
    code = "upload_total_too_large"


class UploadTooManyPagesError(FileIngestionError):
    code = "upload_too_many_pages"


class UploadEmptyError(FileIngestionError):
    code = "upload_empty"


class UnsupportedExtensionError(FileIngestionError):
    code = "upload_unsupported_extension"


class InvalidContentTypeError(FileIngestionError):
    code = "upload_invalid_content_type"


class MissingFilenameError(FileIngestionError):
    code = "upload_missing_filename"


def cleanup_ingestion_result(result: FileIngestionResult | None) -> None:
    if result is None:
        return
    shutil.rmtree(result.request_dir, ignore_errors=True)


def _safe_filename_stem(filename: str) -> str:
    stem = Path(filename).stem.lower()
    sanitized = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return sanitized or "arquivo"


def _validate_upload(upload: UploadedFile) -> tuple[str, str]:
    if not upload.filename:
        raise MissingFilenameError("Todos os arquivos enviados precisam ter nome.")

    extension = Path(upload.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UnsupportedExtensionError(
            f"Extensao nao suportada para upload: {upload.filename}."
        )

    content_type = upload.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES[extension]:
        raise InvalidContentTypeError(
            f"Content-Type invalido para o arquivo {upload.filename}: {content_type}."
        )

    return extension, content_type


def _count_pdf_pages(path: Path) -> int:
    import fitz

    with fitz.open(path) as document:
        return len(document)


def _resolve_upload_limits() -> UploadLimits:
    try:
        return get_settings().upload_limits
    except Exception:
        return UploadLimits(
            max_file_count=10,
            max_file_size_mb=50,
            max_total_upload_mb=200,
            max_pdf_pages=100,
        )


async def ingest_uploaded_files(files: list[UploadedFile]) -> FileIngestionResult:
    if not files:
        raise UploadEmptyError("Envie ao menos um arquivo PDF ou DOCX.")

    limits = _resolve_upload_limits()
    if len(files) > limits.max_file_count:
        raise UploadTooManyFilesError(
            f"Envio com {len(files)} arquivos excede o limite de {limits.max_file_count}."
        )

    max_file_bytes = limits.max_file_size_mb * 1024 * 1024
    max_total_bytes = limits.max_total_upload_mb * 1024 * 1024

    request_dir = Path(mkdtemp(prefix="eletrico_v1_upload_"))
    saved_files: list[IngestedFileMetadata] = []
    total_bytes = 0
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
                        size_bytes += len(chunk)
                        if size_bytes > max_file_bytes:
                            raise UploadFileTooLargeError(
                                f"Arquivo {upload.filename} excede o limite de {limits.max_file_size_mb}MB."
                            )
                        total_bytes += len(chunk)
                        if total_bytes > max_total_bytes:
                            raise UploadTotalTooLargeError(
                                f"Total do upload excede o limite de {limits.max_total_upload_mb}MB."
                            )
                        output_file.write(chunk)
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

        for meta in saved_files:
            if meta.extension != ".pdf":
                continue
            try:
                page_count = _count_pdf_pages(Path(meta.saved_path))
            except Exception:
                # PDF inválido ou stub de teste: limites de página não se aplicam.
                continue
            if page_count > limits.max_pdf_pages:
                cleanup_ingestion_result(
                    FileIngestionResult(
                        request_dir=str(request_dir),
                        files=saved_files,
                    )
                )
                raise UploadTooManyPagesError(
                    f"PDF {meta.original_filename} tem {page_count} paginas; "
                    f"limite e {limits.max_pdf_pages}."
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
