from __future__ import annotations

from pathlib import Path

from app.services.extraction_mapper import (
    ExtractionReport,
    MappingResult,
    assess_extraction_coverage,
    map_extraction_to_partial_context,
)
from app.services.file_ingestion import (
    IngestedFileMetadata,
    UploadedFile,
    cleanup_ingestion_result,
    ingest_uploaded_files,
)
from app.services.memorial_validator import MemorialValidationError
from app.services.pipeline import PipelineResult, generate_memorial_eletrico_v1
from app.services.project_extractor import extract_project_files


def extract_mapping_from_ingested_files(
    files: list[IngestedFileMetadata],
) -> tuple[MappingResult, ExtractionReport]:
    extraction_result = extract_project_files(files)
    mapping = map_extraction_to_partial_context(extraction_result)
    report = assess_extraction_coverage(mapping)
    return mapping, report


def generate_memorial_eletrico_v1_from_ingested_files(
    files: list[IngestedFileMetadata],
    output_path: Path,
) -> PipelineResult:
    extraction_result = extract_project_files(files)
    mapping = map_extraction_to_partial_context(extraction_result)
    report = assess_extraction_coverage(mapping)

    try:
        result = generate_memorial_eletrico_v1(mapping.context, output_path)
        return PipelineResult(
            context=result.context,
            output_path=result.output_path,
            extraction_report=report,
        )
    except MemorialValidationError as error:
        from dataclasses import asdict
        raise MemorialValidationError(
            issues=error.issues,
            extraction_report=asdict(report),
        ) from error


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
