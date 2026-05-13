from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.services.context_builder import build_memorial_glp_v2_context, merge_context
from app.services.diameter_normalizer import normalize_diameter
from app.services.extraction_mapper import (
    ExtractionReport,
    MappingResult,
    assess_extraction_coverage,
    assess_gas_natural_extraction_coverage,
    assess_glp_extraction_coverage,
    assess_glp_v2_extraction_coverage,
    assess_telecom_extraction_coverage,
    map_extraction_to_partial_context,
    map_extraction_to_partial_gas_natural_context,
    map_extraction_to_partial_glp_context,
    map_extraction_to_partial_glp_v2_context,
    map_extraction_to_partial_telecom_context,
)
from app.services.file_ingestion import (
    IngestedFileMetadata,
    UploadedFile,
    cleanup_ingestion_result,
    ingest_uploaded_files,
)
from app.services.llm_extractor import (
    extract_gas_natural_with_llm_result,
    extract_glp_v2_with_llm_result,
    extract_glp_with_llm_result,
    extract_telecom_with_llm_result,
    extract_with_llm_result,
    is_llm_extraction_enabled,
)
from app.services.memorial_validator import MemorialValidationError, ValidationIssue
from app.services.pipeline import (
    PipelineResult,
    generate_memorial_eletrico_v1,
    generate_memorial_gas_natural_v1,
    generate_memorial_glp_v1,
    generate_memorial_glp_v2,
    generate_memorial_telecom_v1,
)
from app.services.project_extractor import ProjectExtractionError, extract_project_files

logger = logging.getLogger(__name__)
_GLP_CONFLICTS_KEY = "_glp_total_points_conflicts"
_GLP_V2_CRITICAL = "_glp_v2_critical_conflicts"
_GLP_AUTHORITATIVE_TOTAL_KEY = "_glp_authoritative_total_points"
_GLP_DIMENSIONAMENTO_FIELDS = ("qtd_fogao", "qtd_aquecedor", "qtd_churrasqueira")


def _attach_cross_validation_report(
    report: ExtractionReport,
    cross_validation: dict[str, Any] | None,
) -> ExtractionReport:
    if not cross_validation:
        return report
    return ExtractionReport(
        filled=report.filled,
        missing=report.missing,
        pending=report.pending,
        evidence=report.evidence,
        cross_validation=cross_validation,
    )

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


def _derive_gas_natural_total_points(context: dict[str, Any]) -> dict[str, Any]:
    dimensionamento = context.get("dimensionamento")
    if not isinstance(dimensionamento, dict):
        return context

    counts = [
        dimensionamento.get("qtd_fogao"),
        dimensionamento.get("qtd_aquecedor"),
        dimensionamento.get("qtd_churrasqueira"),
    ]
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in counts):
        return context

    soma = context.get("soma")
    current_total = soma.get("qtd_pontos_de_utilizacao") if isinstance(soma, dict) else None
    if current_total is not None:
        return context

    return merge_context(
        context,
        {"soma": {"qtd_pontos_de_utilizacao": sum(counts)}},
    )


def _normalize_gas_natural_context(context: dict[str, Any]) -> dict[str, Any]:
    ramal = context.get("ramal")
    normalized_context = context

    if isinstance(ramal, dict):
        ramal_updates: dict[str, Any] = {}

        primario_pavimento = _normalize_glp_pavimento(ramal.get("primario_pavimento"))
        if primario_pavimento is not None:
            ramal_updates["primario_pavimento"] = primario_pavimento

        if ramal_updates:
            normalized_context = merge_context(normalized_context, {"ramal": ramal_updates})

    teto_ou_piso = _normalize_glp_teto_ou_piso(normalized_context.get("teto_ou_piso"))
    if teto_ou_piso is not None:
        normalized_context = merge_context(normalized_context, {"teto_ou_piso": teto_ou_piso})

    return _derive_gas_natural_total_points(normalized_context)


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

    llm_result = extract_with_llm_result(extraction_result.source_files)
    llm_context = llm_result.context
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
    report = _attach_cross_validation_report(report, llm_result.cross_validation)
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

        llm_result = extract_telecom_with_llm_result(extraction_result.source_files)
        llm_context = llm_result.context
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
        report = _attach_cross_validation_report(report, llm_result.cross_validation)
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

        llm_result = extract_gas_natural_with_llm_result(extraction_result.source_files)
        llm_context = llm_result.context
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
        final_context = _normalize_gas_natural_context(final_context)

        mapping = MappingResult(context=final_context, evidence=mapper_mapping.evidence)
        report = assess_gas_natural_extraction_coverage(mapping)
        report = _attach_cross_validation_report(report, llm_result.cross_validation)
        logger.info(
            "Gas natural extraction coverage: filled=%d, missing=%d, pending=%d",
            len(report.filled), len(report.missing), len(report.pending),
        )
        return mapping, report

    extraction_result = extract_project_files(files)
    mapping = map_extraction_to_partial_gas_natural_context(extraction_result)
    mapping = MappingResult(
        context=_normalize_gas_natural_context(mapping.context),
        evidence=mapping.evidence,
    )
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

    llm_result = extract_glp_with_llm_result(extraction_result.source_files)
    llm_context = llm_result.context
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
    report = _attach_cross_validation_report(report, llm_result.cross_validation)
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


def _glp_v2_diameter_from_raw(raw: str | None, regra: str) -> dict[str, Any] | None:
    if not raw or not isinstance(raw, str):
        return None
    nd = normalize_diameter(raw.strip())
    if not nd:
        return None
    return {
        "valor": float(nd.valor),
        "unidade": nd.unidade,
        "valor_formatado": nd.valor_formatado,
        "valor_original": nd.valor_original,
        "fonte_evidencia": [{"regra": regra, "texto": nd.valor_original, "confianca": "medium"}],
    }


def _glp_v2_coalesce_diameter(
    structured: Any,
    raw: str | None,
    regra: str,
) -> dict[str, Any] | None:
    if isinstance(structured, dict):
        v = structured.get("valor")
        if isinstance(v, (int, float)):
            return structured
    return _glp_v2_diameter_from_raw(raw, regra)


def _assemble_glp_v2_payload(
    merged: dict[str, Any],
    mapper_critical: list[dict[str, Any]],
) -> dict[str, Any]:
    work = dict(merged)
    work.pop(_GLP_V2_CRITICAL, None)

    obra = dict(work.get("obra") or {})
    qtd_ap = obra.get("qtd_apartamentos")
    if isinstance(qtd_ap, int) and not isinstance(qtd_ap, bool):
        obra["qtd_apartamentos"] = {
            "valor": qtd_ap,
            "fonte_evidencia": [],
            "confianca": "medium",
        }
    elif isinstance(qtd_ap, dict) and "valor" in qtd_ap:
        qv = qtd_ap["valor"]
        obra["qtd_apartamentos"] = {
            "valor": int(qv),
            "fonte_evidencia": list(qtd_ap.get("fonte_evidencia") or []),
            "confianca": str(qtd_ap.get("confianca") or "medium"),
        }
    else:
        obra["qtd_apartamentos"] = {"valor": 0, "fonte_evidencia": [], "confianca": "low"}

    tanques_in = work.get("tanques") or {}
    if not isinstance(tanques_in, dict):
        tanques_in = {}
    tanques: dict[str, Any] = {
        "quantidade": int(tanques_in.get("quantidade") or 0),
        "fonte_evidencia": list(tanques_in.get("fonte_evidencia") or []),
        "conflitos": list(tanques_in.get("conflitos") or []),
    }
    if tanques_in.get("tipo"):
        tanques["tipo"] = tanques_in["tipo"]
    if tanques_in.get("capacidade_kg") is not None:
        tanques["capacidade_kg"] = float(tanques_in["capacidade_kg"])
    if tanques_in.get("qtd_abrigos") is not None:
        tanques["qtd_abrigos"] = int(tanques_in["qtd_abrigos"])

    ab_raw = work.get("abastecimento") or {}
    if not isinstance(ab_raw, dict):
        ab_raw = {}
    pav = ab_raw.get("pavimento")
    abastecimento: dict[str, Any] = {
        "pavimento": str(pav if pav is not None else "térreo"),
    }
    if ab_raw.get("fonte_evidencia"):
        abastecimento["fonte_evidencia"] = ab_raw["fonte_evidencia"]

    dim = work.get("dimensionamento") or {}
    if not isinstance(dim, dict):
        dim = {}
    dimensionamento = {
        "qtd_fogao": int(dim.get("qtd_fogao") or 0),
        "qtd_aquecedor": int(dim.get("qtd_aquecedor") or 0),
        "qtd_churrasqueira": int(dim.get("qtd_churrasqueira") or 0),
        "qtd_outros": int(dim.get("qtd_outros") or 0),
    }

    pu_in = work.get("pontos_utilizacao") or {}
    if not isinstance(pu_in, dict):
        pu_in = {}
    fog = pu_in.get("fogao")
    if fog is None:
        fog = dimensionamento["qtd_fogao"]
    ch = pu_in.get("churrasqueira")
    if ch is None:
        ch = dimensionamento["qtd_churrasqueira"]
    aq = pu_in.get("aquecedor")
    if aq is None:
        aq = dimensionamento["qtd_aquecedor"]
    outros = pu_in.get("outros")
    if outros is None:
        outros = dimensionamento["qtd_outros"]

    fog_i, ch_i, aq_i, ou_i = int(fog or 0), int(ch or 0), int(aq or 0), int(outros or 0)
    total_calc = fog_i + ch_i + aq_i + ou_i

    pu_conflicts: list[dict[str, Any]] = [
        dict(c) for c in (pu_in.get("conflitos") or []) if isinstance(c, dict)
    ]
    for mc in mapper_critical:
        pu_conflicts.append(dict(mc))

    total_ext = pu_in.get("total_extraido")
    if total_ext is not None and int(total_ext) != total_calc:
        pu_conflicts.append({
            "tipo": "glp_v2_points_total_mismatch",
            "status": "unresolved",
            "valores_observados": [total_ext, total_calc],
            "fontes": ["total_extraido", "total_calculado"],
            "mensagem": "Total extraido difere da soma por tipo.",
        })

    pontos_utilizacao: dict[str, Any] = {
        "fogao": fog_i,
        "churrasqueira": ch_i,
        "aquecedor": aq_i,
        "outros": ou_i,
        "total_extraido": total_ext,
        "total_calculado": total_calc,
        "fontes_evidencia": list(pu_in.get("fontes_evidencia") or []),
        "conflitos": pu_conflicts,
    }

    d_llm = work.get("diametros") or {}
    if not isinstance(d_llm, dict):
        d_llm = {}
    ramal = work.get("ramal") or {}
    if not isinstance(ramal, dict):
        ramal = {}

    tp = d_llm.get("tubulacao_principal")
    raw_main = None
    if isinstance(ramal.get("primario_diametro"), str):
        raw_main = ramal["primario_diametro"]
    if isinstance(tp, str):
        raw_main = tp
    struct_main = tp if isinstance(tp, dict) else None

    main = _glp_v2_coalesce_diameter(struct_main, raw_main, "glp_v2_tubulacao")

    vp = d_llm.get("valvula_esfera")
    raw_valve = vp if isinstance(vp, str) else None
    struct_valve = vp if isinstance(vp, dict) else None
    valve = _glp_v2_coalesce_diameter(struct_valve, raw_valve, "glp_v2_valvula")

    if main is None:
        raise MemorialValidationError(
            issues=[
                ValidationIssue(
                    path="$.diametros.tubulacao_principal",
                    message="Diametro da tubulacao principal ausente apos extracao.",
                    validator="glp_v2_diameter",
                )
            ],
            extraction_report=None,
        )

    if valve is None:
        valve = {**main, "inferido": True}

    ramal_out = {
        "primario_material": str(ramal.get("primario_material") or "não especificado"),
        "primario_pavimento": str(ramal.get("primario_pavimento") or "térreo"),
    }

    numero = work.get("numero") or {}
    if not isinstance(numero, dict):
        numero = {}
    numero_out = {"prancha": str(numero.get("prancha") or "01/01")}

    teto = work.get("teto_ou_piso")
    if not teto:
        teto = "piso"

    return {
        "obra": obra,
        "tanques": tanques,
        "abastecimento": abastecimento,
        "dimensionamento": dimensionamento,
        "pontos_utilizacao": pontos_utilizacao,
        "diametros": {"tubulacao_principal": main, "valvula_esfera": valve},
        "ramal": ramal_out,
        "numero": numero_out,
        "teto_ou_piso": str(teto),
    }


def extract_glp_v2_mapping_from_ingested_files(
    files: list[IngestedFileMetadata],
) -> tuple[MappingResult, ExtractionReport]:
    if not is_llm_extraction_enabled():
        raise ProjectExtractionError(
            "Geracao do memorial GLP v2 a partir de arquivos requer extracao LLM habilitada "
            "(defina USE_LLM_EXTRACTION)."
        )

    extraction_result = extract_project_files(files)
    llm_result = extract_glp_v2_with_llm_result(extraction_result.source_files)
    llm_context = llm_result.context

    mapper_mapping = map_extraction_to_partial_glp_v2_context(extraction_result)
    mapper_ctx = dict(mapper_mapping.context)
    critical = list(mapper_ctx.pop(_GLP_V2_CRITICAL, []) or [])

    gap_fills = _fill_gaps(llm_context, mapper_ctx)
    merged = merge_context(llm_context, gap_fills) if gap_fills else llm_context

    merged = _normalize_glp_non_total_fields(merged)

    assess_ctx = MappingResult(context=dict(merged), evidence=mapper_mapping.evidence)
    report = assess_glp_v2_extraction_coverage(assess_ctx)
    report = _attach_cross_validation_report(report, llm_result.cross_validation)

    assembled = _assemble_glp_v2_payload(merged, critical)
    mapping = MappingResult(context=assembled, evidence=mapper_mapping.evidence)
    logger.info(
        "GLP v2 extraction coverage: filled=%d, missing=%d, pending=%d",
        len(report.filled), len(report.missing), len(report.pending),
    )
    return mapping, report


def generate_memorial_glp_v2_from_ingested_files(
    files: list[IngestedFileMetadata],
    output_path: Path,
) -> PipelineResult:
    mapping, report = extract_glp_v2_mapping_from_ingested_files(files)
    context_payload = mapping.context

    unresolved = [
        c for c in context_payload.get("pontos_utilizacao", {}).get("conflitos", [])
        if isinstance(c, dict) and c.get("status") == "unresolved"
    ]
    if unresolved:
        raise MemorialValidationError(
            issues=[
                ValidationIssue(
                    path="$.pontos_utilizacao.conflitos",
                    message="Conflitos criticos GLP v2 sem resolucao.",
                    validator="glp_v2_conflict",
                )
            ],
            extraction_report=_build_extraction_report_payload(report, unresolved),
        )

    try:
        result = generate_memorial_glp_v2(context_payload, output_path)
        return PipelineResult(
            context=result.context,
            output_path=result.output_path,
            extraction_report=report,
        )
    except MemorialValidationError as error:
        raise MemorialValidationError(
            issues=error.issues,
            extraction_report=_build_extraction_report_payload(report, None),
        ) from error


async def generate_memorial_glp_v2_from_uploaded_files(
    files: list[UploadedFile],
    output_path: Path,
) -> PipelineResult:
    ingestion_result = await ingest_uploaded_files(files)
    try:
        return generate_memorial_glp_v2_from_ingested_files(
            ingestion_result.files,
            output_path,
        )
    finally:
        cleanup_ingestion_result(ingestion_result)


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
