from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.services.context_builder import merge_context
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
from app.services.llm_extractor import extract_with_llm
from app.services.memorial_validator import MemorialValidationError
from app.services.pipeline import PipelineResult, generate_memorial_eletrico_v1
from app.services.project_extractor import extract_project_files

logger = logging.getLogger(__name__)


def _fill_gaps(base: dict[str, Any], supplement: dict[str, Any]) -> dict[str, Any]:
    """Supplement fills only fields that are missing or None in base."""
    filled: dict[str, Any] = {}
    for section_key, section_value in supplement.items():
        if not isinstance(section_value, dict):
            continue
        base_section = base.get(section_key, {})
        if not isinstance(base_section, dict):
            continue
        section_fills: dict[str, Any] = {}
        for field_key, field_value in section_value.items():
            if base_section.get(field_key) is None and field_value is not None:
                section_fills[field_key] = field_value
        if section_fills:
            filled[section_key] = section_fills
    return filled


def extract_mapping_from_ingested_files(
    files: list[IngestedFileMetadata],
) -> tuple[MappingResult, ExtractionReport]:
    return _extract_and_combine(files)


def _extract_and_combine(
    files: list[IngestedFileMetadata],
) -> tuple[MappingResult, ExtractionReport]:
    """Shared extraction logic: mapper first, LLM fills gaps."""
    extraction_result = extract_project_files(files)
    mapping = map_extraction_to_partial_context(extraction_result)

    mapper_fields = sum(
        len(s) for s in mapping.context.values() if isinstance(s, dict)
    )
    logger.info("Mapper extracted %d fields from %d files", mapper_fields, len(files))

    llm_context = extract_with_llm(extraction_result.source_files)
    if llm_context:
        gap_fills = _fill_gaps(mapping.context, llm_context)
        if gap_fills:
            llm_filled = sum(len(s) for s in gap_fills.values() if isinstance(s, dict))
            logger.info("LLM filled %d gap fields", llm_filled)
            merged = merge_context(mapping.context, gap_fills)
            mapping = MappingResult(context=merged, evidence=mapping.evidence)

    report = assess_extraction_coverage(mapping)
    logger.info(
        "Extraction coverage: filled=%d, missing=%d, pending=%d",
        len(report.filled), len(report.missing), len(report.pending),
    )
    return mapping, report


def generate_memorial_eletrico_v1_from_ingested_files(
    files: list[IngestedFileMetadata],
    output_path: Path,
) -> PipelineResult:
    mapping, report = _extract_and_combine(files)

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
