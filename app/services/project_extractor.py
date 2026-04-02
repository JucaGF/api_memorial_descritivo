from __future__ import annotations

import base64
import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.services.file_ingestion import IngestedFileMetadata

logger = logging.getLogger(__name__)

IMAGE_DPI = 200


@dataclass(frozen=True)
class ExtractedSourceFile:
    original_filename: str
    stored_filename: str
    extension: str
    saved_path: str
    extracted_text: str
    page_images: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectExtractionResult:
    raw_text: str
    source_files: list[ExtractedSourceFile]
    signals: dict[str, object]


class ProjectExtractionError(Exception):
    pass


MIN_EXTRACTABLE_CHARACTERS = 100


def has_pdf_extractor_dependency() -> bool:
    return importlib.util.find_spec("fitz") is not None


def has_docx_extractor_dependency() -> bool:
    return importlib.util.find_spec("docx") is not None


def _extract_docx_text(file_path: Path) -> str:
    if not has_docx_extractor_dependency():
        raise ProjectExtractionError(
            "Extracao de DOCX indisponivel: instale python-docx para processar arquivos DOCX."
        )

    try:
        from docx import Document

        document = Document(str(file_path))
    except Exception as error:
        raise ProjectExtractionError(
            f"Falha ao ler DOCX {file_path.name}: arquivo corrompido ou ilegivel."
        ) from error

    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs]
    return "\n".join(paragraph for paragraph in paragraphs if paragraph)


def _extract_pdf_text_and_images(file_path: Path) -> tuple[str, list[str]]:
    if not has_pdf_extractor_dependency():
        raise ProjectExtractionError(
            "Extracao de PDF indisponivel: instale PyMuPDF para processar arquivos PDF."
        )

    try:
        import fitz

        pages: list[str] = []
        images: list[str] = []
        with fitz.open(file_path) as document:
            for page in document:
                pages.append(page.get_text("text").strip())
                pixmap = page.get_pixmap(dpi=IMAGE_DPI)
                png_bytes = pixmap.tobytes("png")
                b64 = base64.b64encode(png_bytes).decode("ascii")
                images.append(f"data:image/png;base64,{b64}")
    except Exception as error:
        raise ProjectExtractionError(
            f"Falha ao ler PDF {file_path.name}: arquivo corrompido ou ilegivel."
        ) from error

    text = "\n".join(page for page in pages if page)
    logger.info("PDF %s: %d pages, %d images extracted", file_path.name, len(pages), len(images))
    return text, images


def _extract_by_extension(file_path: Path, extension: str) -> tuple[str, list[str]]:
    if extension == ".docx":
        return _extract_docx_text(file_path), []
    if extension == ".pdf":
        return _extract_pdf_text_and_images(file_path)
    raise ProjectExtractionError(f"Extensao nao suportada para extracao: {extension}.")


def extract_project_files(
    files: list[IngestedFileMetadata],
) -> ProjectExtractionResult:
    extracted_files: list[ExtractedSourceFile] = []

    for file_metadata in files:
        file_path = Path(file_metadata.saved_path)
        if not file_path.exists():
            raise ProjectExtractionError(
                f"Arquivo persistido nao encontrado para extracao: {file_path}."
            )

        extracted_text, page_images = _extract_by_extension(file_path, file_metadata.extension)
        extracted_files.append(
            ExtractedSourceFile(
                original_filename=file_metadata.original_filename,
                stored_filename=file_metadata.stored_filename,
                extension=file_metadata.extension,
                saved_path=file_metadata.saved_path,
                extracted_text=extracted_text,
                page_images=page_images,
            )
        )

    raw_text = "\n\n".join(
        source_file.extracted_text for source_file in extracted_files if source_file.extracted_text
    )

    has_images = any(sf.page_images for sf in extracted_files)
    if len(raw_text) < MIN_EXTRACTABLE_CHARACTERS and not has_images:
        raise ProjectExtractionError(
            "Texto insuficiente extraído dos arquivos enviados. "
            "Verifique se os PDFs contêm texto selecionável (não são imagens escaneadas)."
        )

    signals = {
        "total_files": len(extracted_files),
        "file_types": [source_file.extension for source_file in extracted_files],
        "has_pdf": any(source_file.extension == ".pdf" for source_file in extracted_files),
        "has_docx": any(source_file.extension == ".docx" for source_file in extracted_files),
        "total_characters": len(raw_text),
    }
    return ProjectExtractionResult(
        raw_text=raw_text,
        source_files=extracted_files,
        signals=signals,
    )
