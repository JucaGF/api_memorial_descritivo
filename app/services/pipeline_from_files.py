from __future__ import annotations

from pathlib import Path

from app.services.extraction_mapper import map_extraction_to_partial_context
from app.services.file_ingestion import (
    IngestedFileMetadata,
    UploadedFile,
    cleanup_ingestion_result,
    ingest_uploaded_files,
)
from app.services.pipeline import PipelineResult, generate_memorial_eletrico_v1
from app.services.project_extractor import extract_project_files


def generate_memorial_eletrico_v1_from_ingested_files(
    files: list[IngestedFileMetadata],
    output_path: Path,
) -> PipelineResult:
    extraction_result = extract_project_files(files)
    partial_context = map_extraction_to_partial_context(extraction_result)
    return generate_memorial_eletrico_v1(partial_context, output_path)


async def generate_memorial_eletrico_v1_from_uploaded_files(
    files: list[UploadedFile],
    output_path: Path,
) -> PipelineResult:
    ingestion_result = await ingest_uploaded_files(files)
    try:
        return generate_memorial_eletrico_v1_from_ingested_files(
            ingestion_result.files,
            output_path,
        )
    finally:
        cleanup_ingestion_result(ingestion_result)
