from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from app.services.context_builder import build_memorial_eletrico_v1_context
from app.services.extraction_mapper import map_extraction_to_partial_context
from app.services.file_ingestion import (
    IngestedFileMetadata,
    cleanup_ingestion_result,
    ingest_uploaded_files,
)
from app.services.memorial_renderer import render_memorial_eletrico_v1
from app.services.memorial_validator import validate_memorial_eletrico_v1_context
from app.services.pipeline import PipelineResult
from app.services.project_extractor import extract_project_files


def generate_memorial_eletrico_v1_from_ingested_files(
    files: list[IngestedFileMetadata],
    output_path: Path,
) -> PipelineResult:
    extraction_result = extract_project_files(files)
    partial_context = map_extraction_to_partial_context(extraction_result)
    context = build_memorial_eletrico_v1_context(partial_context)
    validate_memorial_eletrico_v1_context(context)
    rendered_output_path = render_memorial_eletrico_v1(context, output_path)
    return PipelineResult(context=context, output_path=rendered_output_path)


async def generate_memorial_eletrico_v1_from_uploaded_files(
    files: list[UploadFile],
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
