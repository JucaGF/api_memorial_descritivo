from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.services.context_builder import merge_context
from app.services.extraction_mapper import (
    ExtractionReport,
    MappingResult,
    assess_extraction_coverage,
    assess_gas_natural_extraction_coverage,
    assess_glp_extraction_coverage,
    assess_telecom_extraction_coverage,
    map_extraction_to_partial_context,
    map_extraction_to_partial_gas_natural_context,
    map_extraction_to_partial_glp_context,
    map_extraction_to_partial_telecom_context,
)
from app.services.file_ingestion import (
    IngestedFileMetadata,
    UploadedFile,
    cleanup_ingestion_result,
    ingest_uploaded_files,
)
from app.services.llm_extractor import (
    extract_gas_natural_with_llm,
    extract_glp_with_llm,
    extract_telecom_with_llm,
    extract_with_llm,
    is_llm_extraction_enabled,
)
from app.services.memorial_validator import MemorialValidationError, ValidationIssue
from app.services.pipeline import (
    PipelineResult,
    generate_memorial_eletrico_v1,
    generate_memorial_gas_natural_v1,
    generate_memorial_glp_v1,
    generate_memorial_telecom_v1,
)
from app.services.project_extractor import ProjectExtractionError, extract_project_files

logger = logging.getLogger(__name__)
_GLP_CONFLICTS_KEY = "_glp_total_points_conflicts"
_GLP_AUTHORITATIVE_TOTAL_KEY = "_glp_authoritative_total_points"
_GLP_DIMENSIONAMENTO_FIELDS = ("qtd_fogao", "qtd_aquecedor", "qtd_churrasqueira")
_FRACTIONAL_INCH_RE = re.compile(
    r'^\s*(?:(?P<whole>\d+)\s+)?(?:(?P<num>\d+)\s*/\s*(?P<den>\d+)|(?P<decimal>\d+(?:[.,]\d+)?))\s*(?:"|pol(?:egadas?)?)\s*$',
    re.IGNORECASE,
)
_MM_VALUE_RE = re.compile(r"^\s*(?P<value>\d+(?:[.,]\d+)?)\s*mm\s*$", re.IGNORECASE)


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


def _apply_glp_authoritative_mapper_overrides(
    context: dict[str, Any],
    mapper_context: dict[str, Any],
) -> dict[str, Any]:
    soma = mapper_context.get("soma")
    if not isinstance(soma, dict):
        return context

    total_points = soma.get("qtd_pontos_de_utilizacao")
    if not isinstance(total_points, int) or isinstance(total_points, bool):
        return context

    overridden = merge_context(
        context,
        {"soma": {"qtd_pontos_de_utilizacao": total_points}},
    )
    overridden[_GLP_AUTHORITATIVE_TOTAL_KEY] = total_points
    return overridden


def _parse_diameter_mm(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return None

    mm_match = _MM_VALUE_RE.match(value)
    if mm_match:
        return round(float(mm_match.group("value").replace(",", ".")), 1)

    inch_match = _FRACTIONAL_INCH_RE.match(value)
    if not inch_match:
        return None

    whole = int(inch_match.group("whole") or 0)
    decimal = inch_match.group("decimal")
    if decimal is not None:
        inches = whole + float(decimal.replace(",", "."))
    else:
        numerator = int(inch_match.group("num"))
        denominator = int(inch_match.group("den"))
        inches = whole + (numerator / denominator)

    return round(inches * 25.4, 1)


def _normalize_glp_pavimento(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    stripped = re.sub(r"\s+", " ", value).strip()
    normalized = unicodedata.normalize("NFKD", stripped).encode("ascii", "ignore").decode("ascii")
    key = re.sub(r"[^a-z0-9]+", "", normalized.casefold())

    if "terreo" in key:
        return "térreo"
    if "subsolo" in key:
        return "subsolo"
    return stripped


def _normalize_glp_teto_ou_piso(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    stripped = re.sub(r"\s+", " ", value).strip()
    normalized = unicodedata.normalize("NFKD", stripped).encode("ascii", "ignore").decode("ascii")
    key = re.sub(r"[^a-z0-9]+", "", normalized.casefold())

    if "enterrado" in key:
        return "enterrado"
    if "contrapiso" in key:
        return "contrapiso"
    if "teto" in key:
        return "teto"
    if "piso" in key:
        return "piso"
    return stripped


def _reconcile_glp_total_points(
    context: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    dimensionamento = context.get("dimensionamento")
    soma = context.get("soma")
    if not isinstance(dimensionamento, dict) or not isinstance(soma, dict):
        return context, []

    reported_total = soma.get("qtd_pontos_de_utilizacao")
    if not isinstance(reported_total, int) or isinstance(reported_total, bool):
        return context, []
    authoritative_total = context.get(_GLP_AUTHORITATIVE_TOTAL_KEY)
    has_authoritative_total = (
        isinstance(authoritative_total, int)
        and not isinstance(authoritative_total, bool)
    )

    counts_payload = {
        field_name: dimensionamento.get(field_name)
        for field_name in _GLP_DIMENSIONAMENTO_FIELDS
    }
    counts = [
        value for value in counts_payload.values()
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    has_known_counts = bool(counts)
    is_complete = len(counts) == len(_GLP_DIMENSIONAMENTO_FIELDS)

    if not is_complete:
        known_total = sum(counts)
        if has_known_counts and known_total != reported_total:
            if has_authoritative_total and reported_total == authoritative_total:
                return context, [
                    {
                        "type": "glp_total_points_conflict",
                        "status": "resolved",
                        "field": "soma.qtd_pontos_de_utilizacao",
                        "reported_total": reported_total,
                        "dimensionamento_counts": counts_payload,
                        "known_dimensionamento_total": known_total,
                        "deterministic_total": authoritative_total,
                        "reason": "quantitative_table_authoritative",
                    }
                ]
            return context, [
                {
                    "type": "glp_total_points_conflict",
                    "status": "unresolved",
                    "field": "soma.qtd_pontos_de_utilizacao",
                    "reported_total": reported_total,
                    "dimensionamento_counts": counts_payload,
                    "known_dimensionamento_total": known_total,
                    "deterministic_total": None,
                    "reason": "dimensionamento_incomplete",
                }
            ]
        return context, []

    deterministic_total = sum(counts)
    if reported_total == deterministic_total:
        return context, []
    if has_authoritative_total and reported_total == authoritative_total:
        return context, [
            {
                "type": "glp_total_points_conflict",
                "status": "resolved",
                "field": "soma.qtd_pontos_de_utilizacao",
                "reported_total": reported_total,
                "dimensionamento_counts": counts_payload,
                "known_dimensionamento_total": deterministic_total,
                "deterministic_total": authoritative_total,
                "reason": "quantitative_table_authoritative",
            }
        ]

    return merge_context(context, {"soma": {"qtd_pontos_de_utilizacao": deterministic_total}}), [
        {
            "type": "glp_total_points_conflict",
            "status": "resolved",
            "field": "soma.qtd_pontos_de_utilizacao",
            "reported_total": reported_total,
            "dimensionamento_counts": counts_payload,
            "known_dimensionamento_total": deterministic_total,
            "deterministic_total": deterministic_total,
            "reason": "dimensionamento_complete",
        }
    ]


def _normalize_glp_non_total_fields(context: dict[str, Any]) -> dict[str, Any]:
    ramal = context.get("ramal")
    normalized_context = context

    if isinstance(ramal, dict):
        ramal_updates: dict[str, Any] = {}

        diametro = ramal.get("primario_diametro")
        normalized_diameter = _parse_diameter_mm(diametro)
        if normalized_diameter is not None:
            ramal_updates["primario_diametro"] = normalized_diameter

        primario_pavimento = _normalize_glp_pavimento(ramal.get("primario_pavimento"))
        if primario_pavimento is not None:
            ramal_updates["primario_pavimento"] = primario_pavimento

        if ramal_updates:
            normalized_context = merge_context(normalized_context, {"ramal": ramal_updates})

    teto_ou_piso = _normalize_glp_teto_ou_piso(normalized_context.get("teto_ou_piso"))
    if teto_ou_piso is not None:
        normalized_context = merge_context(normalized_context, {"teto_ou_piso": teto_ou_piso})

    return normalized_context


def _normalize_glp_context(context: dict[str, Any]) -> dict[str, Any]:
    normalized_context = _normalize_glp_non_total_fields(context)
    reconciled_context, _ = _reconcile_glp_total_points(normalized_context)
    return reconciled_context


def _attach_glp_conflicts(
    context: dict[str, Any],
    conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    if not conflicts:
        return context

    context_with_conflicts = dict(context)
    context_with_conflicts[_GLP_CONFLICTS_KEY] = conflicts
    return context_with_conflicts


def _detach_glp_conflicts(
    context: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    conflicts = context.get(_GLP_CONFLICTS_KEY)
    if not isinstance(conflicts, list):
        clean_context = dict(context)
        clean_context.pop(_GLP_AUTHORITATIVE_TOTAL_KEY, None)
        return clean_context, []

    clean_context = dict(context)
    clean_context.pop(_GLP_CONFLICTS_KEY, None)
    clean_context.pop(_GLP_AUTHORITATIVE_TOTAL_KEY, None)
    return clean_context, conflicts


def _build_extraction_report_payload(
    report: ExtractionReport,
    conflicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = asdict(report)
    if conflicts:
        payload["conflicts"] = conflicts
    return payload


def _extract_llm_primary(
    files: list[IngestedFileMetadata],
) -> tuple[MappingResult, ExtractionReport]:
    """LLM vision is the primary extractor; mapper supplements remaining gaps."""
    extraction_result = extract_project_files(files)

    llm_context = extract_with_llm(extraction_result.source_files)
    llm_fields = sum(
        1 for section in llm_context.values()
        if isinstance(section, dict)
        for v in section.values()
        if v is not None
    )
    logger.info("LLM primary extracted %d fields from %d files", llm_fields, len(files))

    mapper_mapping = map_extraction_to_partial_context(extraction_result)
    gap_fills = _fill_gaps(llm_context, mapper_mapping.context)
    if gap_fills:
        gap_count = sum(len(s) for s in gap_fills.values() if isinstance(s, dict))
        logger.info("Mapper supplemented %d additional fields", gap_count)
        final_context = merge_context(llm_context, gap_fills)
    else:
        final_context = llm_context

    mapping = MappingResult(context=final_context, evidence=mapper_mapping.evidence)
    report = assess_extraction_coverage(mapping)
    logger.info(
        "Extraction coverage: filled=%d, missing=%d, pending=%d",
        len(report.filled), len(report.missing), len(report.pending),
    )
    return mapping, report


def _extract_mapper_only(
    files: list[IngestedFileMetadata],
) -> tuple[MappingResult, ExtractionReport]:
    """Deterministic mapper extraction (fallback when LLM is disabled)."""
    extraction_result = extract_project_files(files)
    mapping = map_extraction_to_partial_context(extraction_result)

    mapper_fields = sum(
        len(s) for s in mapping.context.values() if isinstance(s, dict)
    )
    logger.info("Mapper extracted %d fields from %d files", mapper_fields, len(files))

    report = assess_extraction_coverage(mapping)
    logger.info(
        "Extraction coverage: filled=%d, missing=%d, pending=%d",
        len(report.filled), len(report.missing), len(report.pending),
    )
    return mapping, report


def extract_mapping_from_ingested_files(
    files: list[IngestedFileMetadata],
) -> tuple[MappingResult, ExtractionReport]:
    if is_llm_extraction_enabled():
        return _extract_llm_primary(files)
    return _extract_mapper_only(files)


def extract_telecom_mapping_from_ingested_files(
    files: list[IngestedFileMetadata],
) -> tuple[MappingResult, ExtractionReport]:
    if is_llm_extraction_enabled():
        extraction_result = extract_project_files(files)

        llm_context = extract_telecom_with_llm(extraction_result.source_files)
        llm_fields = sum(
            1 for section in llm_context.values()
            if isinstance(section, dict)
            for v in section.values()
            if v is not None
        )
        logger.info("Telecom LLM primary extracted %d fields from %d files", llm_fields, len(files))

        mapper_mapping = map_extraction_to_partial_telecom_context(extraction_result)
        gap_fills = _fill_gaps(llm_context, mapper_mapping.context)
        if gap_fills:
            gap_count = sum(len(s) for s in gap_fills.values() if isinstance(s, dict))
            logger.info("Telecom mapper supplemented %d additional fields", gap_count)
            final_context = merge_context(llm_context, gap_fills)
        else:
            final_context = llm_context

        mapping = MappingResult(context=final_context, evidence=mapper_mapping.evidence)
        report = assess_telecom_extraction_coverage(mapping)
        logger.info(
            "Telecom extraction coverage: filled=%d, missing=%d, pending=%d",
            len(report.filled), len(report.missing), len(report.pending),
        )
        return mapping, report

    extraction_result = extract_project_files(files)
    mapping = map_extraction_to_partial_telecom_context(extraction_result)
    report = assess_telecom_extraction_coverage(mapping)
    logger.info(
        "Telecom extraction coverage: filled=%d, missing=%d, pending=%d",
        len(report.filled), len(report.missing), len(report.pending),
    )
    return mapping, report


def extract_gas_natural_mapping_from_ingested_files(
    files: list[IngestedFileMetadata],
) -> tuple[MappingResult, ExtractionReport]:
    if is_llm_extraction_enabled():
        extraction_result = extract_project_files(files)

        llm_context = extract_gas_natural_with_llm(extraction_result.source_files)
        llm_fields = sum(
            1 for section in llm_context.values()
            if isinstance(section, dict)
            for v in section.values()
            if v is not None
        )
        logger.info("Gas natural LLM primary extracted %d fields from %d files", llm_fields, len(files))

        mapper_mapping = map_extraction_to_partial_gas_natural_context(extraction_result)
        gap_fills = _fill_gaps(llm_context, mapper_mapping.context)
        if gap_fills:
            gap_count = sum(len(s) for s in gap_fills.values() if isinstance(s, dict))
            logger.info("Gas natural mapper supplemented %d additional fields", gap_count)
            final_context = merge_context(llm_context, gap_fills)
        else:
            final_context = llm_context

        mapping = MappingResult(context=final_context, evidence=mapper_mapping.evidence)
        report = assess_gas_natural_extraction_coverage(mapping)
        logger.info(
            "Gas natural extraction coverage: filled=%d, missing=%d, pending=%d",
            len(report.filled), len(report.missing), len(report.pending),
        )
        return mapping, report

    extraction_result = extract_project_files(files)
    mapping = map_extraction_to_partial_gas_natural_context(extraction_result)
    report = assess_gas_natural_extraction_coverage(mapping)
    logger.info(
        "Gas natural extraction coverage: filled=%d, missing=%d, pending=%d",
        len(report.filled), len(report.missing), len(report.pending),
    )
    return mapping, report


def generate_memorial_eletrico_v1_from_ingested_files(
    files: list[IngestedFileMetadata],
    output_path: Path,
) -> PipelineResult:
    mapping, report = extract_mapping_from_ingested_files(files)

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


def generate_memorial_telecom_v1_from_ingested_files(
    files: list[IngestedFileMetadata],
    output_path: Path,
) -> PipelineResult:
    mapping, report = extract_telecom_mapping_from_ingested_files(files)

    try:
        result = generate_memorial_telecom_v1(mapping.context, output_path)
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


async def generate_memorial_telecom_v1_from_uploaded_files(
    files: list[UploadedFile],
    output_path: Path,
) -> PipelineResult:
    ingestion_result = await ingest_uploaded_files(files)
    try:
        return generate_memorial_telecom_v1_from_ingested_files(
            ingestion_result.files,
            output_path,
        )
    finally:
        cleanup_ingestion_result(ingestion_result)


def generate_memorial_gas_natural_v1_from_ingested_files(
    files: list[IngestedFileMetadata],
    output_path: Path,
) -> PipelineResult:
    mapping, report = extract_gas_natural_mapping_from_ingested_files(files)

    try:
        result = generate_memorial_gas_natural_v1(mapping.context, output_path)
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


async def generate_memorial_gas_natural_v1_from_uploaded_files(
    files: list[UploadedFile],
    output_path: Path,
) -> PipelineResult:
    ingestion_result = await ingest_uploaded_files(files)
    try:
        return generate_memorial_gas_natural_v1_from_ingested_files(
            ingestion_result.files,
            output_path,
        )
    finally:
        cleanup_ingestion_result(ingestion_result)


def extract_glp_mapping_from_ingested_files(
    files: list[IngestedFileMetadata],
) -> tuple[MappingResult, ExtractionReport]:
    if not is_llm_extraction_enabled():
        raise ProjectExtractionError(
            "Geracao do memorial GLP a partir de arquivos requer extracao LLM habilitada "
            "(defina USE_LLM_EXTRACTION)."
        )

    extraction_result = extract_project_files(files)

    llm_context = extract_glp_with_llm(extraction_result.source_files)
    llm_fields = sum(
        1 for section in llm_context.values()
        if isinstance(section, dict)
        for v in section.values()
        if v is not None
    )
    logger.info("GLP LLM primary extracted %d fields from %d files", llm_fields, len(files))

    mapper_mapping = map_extraction_to_partial_glp_context(extraction_result)
    gap_fills = _fill_gaps(llm_context, mapper_mapping.context)
    if gap_fills:
        gap_count = sum(len(s) for s in gap_fills.values() if isinstance(s, dict))
        logger.info("GLP mapper supplemented %d additional fields", gap_count)
        final_context = merge_context(llm_context, gap_fills)
    else:
        final_context = llm_context

    final_context = _apply_glp_authoritative_mapper_overrides(
        final_context,
        mapper_mapping.context,
    )

    final_context = _normalize_glp_non_total_fields(final_context)
    final_context, conflicts = _reconcile_glp_total_points(final_context)
    final_context = _attach_glp_conflicts(final_context, conflicts)

    mapping = MappingResult(context=final_context, evidence=mapper_mapping.evidence)
    report = assess_glp_extraction_coverage(mapping)
    logger.info(
        "GLP extraction coverage: filled=%d, missing=%d, pending=%d",
        len(report.filled), len(report.missing), len(report.pending),
    )
    return mapping, report


def generate_memorial_glp_v1_from_ingested_files(
    files: list[IngestedFileMetadata],
    output_path: Path,
) -> PipelineResult:
    mapping, report = extract_glp_mapping_from_ingested_files(files)
    context, conflicts = _detach_glp_conflicts(mapping.context)

    unresolved_conflicts = [
        conflict for conflict in conflicts
        if conflict.get("status") == "unresolved"
    ]
    if unresolved_conflicts:
        raise MemorialValidationError(
            issues=[
                ValidationIssue(
                    path="$.soma.qtd_pontos_de_utilizacao",
                    message="Conflito GLP em qtd_pontos_de_utilizacao sem resolucao deterministica.",
                    validator="glp_conflict",
                )
            ],
            extraction_report=_build_extraction_report_payload(report, conflicts),
        )

    try:
        result = generate_memorial_glp_v1(context, output_path)
        return PipelineResult(
            context=result.context,
            output_path=result.output_path,
            extraction_report=report,
        )
    except MemorialValidationError as error:
        raise MemorialValidationError(
            issues=error.issues,
            extraction_report=_build_extraction_report_payload(report, conflicts),
        ) from error


async def generate_memorial_glp_v1_from_uploaded_files(
    files: list[UploadedFile],
    output_path: Path,
) -> PipelineResult:
    ingestion_result = await ingest_uploaded_files(files)
    try:
        return generate_memorial_glp_v1_from_ingested_files(
            ingestion_result.files,
            output_path,
        )
    finally:
        cleanup_ingestion_result(ingestion_result)
