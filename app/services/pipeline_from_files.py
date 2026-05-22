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
from app.services.quantitative_extraction import (
    GlpV2QuantitativeResult,
    QuantitativeCandidate,
    extract_glp_v2_quantitative_candidates,
    resolve_glp_v2_quantitatives,
)

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


def _apply_glp_v2_mapper_overrides(
    context: dict[str, Any],
    mapper_context: dict[str, Any],
) -> dict[str, Any]:
    obra = mapper_context.get("obra")
    if not isinstance(obra, dict):
        return context

    tipologia = obra.get("tipologia")
    if not isinstance(tipologia, str) or not tipologia.strip():
        return context

    return merge_context(context, {"obra": {"tipologia": tipologia.strip()}})


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


def _attach_glp_v2_quantitative_report(
    report: ExtractionReport,
    quantitative_result: GlpV2QuantitativeResult,
) -> ExtractionReport:
    cross_validation = dict(report.cross_validation or {})
    cross_validation.update(quantitative_result.to_cross_validation_payload())
    return _attach_cross_validation_report(report, cross_validation)


_AUTHORITATIVE_QUANTITATIVE_FIELDS = {
    "eletrico": {
        "obra.qtd_apartamentos",
        "aterramento.qtd_hastes",
        "aterramento.secao_cabo_cobre_mm2",
        "mt.tensao_kv",
        "mt.secao_cabo_mm2",
        "gerador.tem_gerador",
    },
    "gas_natural": {
        "obra.qtd_apartamentos",
        "dimensionamento.qtd_fogao",
        "dimensionamento.qtd_aquecedor",
        "dimensionamento.qtd_churrasqueira",
        "soma.qtd_pontos_de_utilizacao",
    },
}


def _get_path(context: dict[str, Any], path: str) -> Any:
    value: Any = context
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _set_path(context: dict[str, Any], path: str, value: Any) -> None:
    target = context
    keys = path.split(".")
    for key in keys[:-1]:
        section = target.get(key)
        if not isinstance(section, dict):
            section = {}
            target[key] = section
        target = section
    target[keys[-1]] = value


def _quantitative_candidate_from_evidence(
    *,
    memorial_type: str,
    field_path: str,
    value: Any,
    evidence: Any,
) -> QuantitativeCandidate:
    return QuantitativeCandidate(
        field_path=field_path,
        value=value,
        unit=None,
        entity=field_path,
        memorial_type=memorial_type,
        source_file=None,
        page_number=None,
        source_kind="deterministic_mapper",
        extraction_method=str(getattr(evidence, "rule", "mapper")),
        evidence_text=getattr(evidence, "evidence", None),
        confidence=str(getattr(evidence, "confidence", "medium")),
    )


def _ascii_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _is_schematic_apartment_source(source_file: Any) -> bool:
    filename = str(getattr(source_file, "original_filename", "") or "")
    text = str(getattr(source_file, "extracted_text", "") or "")
    filename_key = _ascii_text(filename)
    text_key = _ascii_text(text[:1200])
    if any(marker in filename_key for marker in ("corte", "esquematico", "diagrama")):
        return True
    return bool(re.search(r"\bcor(?:te)?\s+esquematico\b", text_key))


def _extract_schematic_apartment_ids(extraction_result: Any) -> tuple[set[int], list[str]]:
    apartment_ids: set[int] = set()
    source_names: list[str] = []
    for source_file in list(getattr(extraction_result, "source_files", []) or []):
        if not _is_schematic_apartment_source(source_file):
            continue
        text = str(getattr(source_file, "extracted_text", "") or "")
        ids = {
            int(match)
            for match in re.findall(r"\bAPTO\s*0?(\d{3})\b", text, flags=re.IGNORECASE)
        }
        ids = {apt for apt in ids if apt // 100 >= 1}
        if not ids:
            continue
        apartment_ids.update(ids)
        filename = str(getattr(source_file, "original_filename", "") or "")
        if filename:
            source_names.append(filename)
    return apartment_ids, source_names


def _apply_schematic_apartment_count_override(
    context: dict[str, Any],
    extraction_result: Any,
    *,
    memorial_type: str,
) -> tuple[dict[str, Any], list[QuantitativeCandidate], list[dict[str, Any]], list[dict[str, Any]]]:
    apartment_ids, source_names = _extract_schematic_apartment_ids(extraction_result)
    if not apartment_ids:
        return context, [], [], []

    value = len(apartment_ids)
    source_file = ", ".join(source_names) if source_names else None
    evidence_text = (
        f"{value} apartamentos identificados no corte "
        f"(APTO {min(apartment_ids):03d} a APTO {max(apartment_ids):03d})"
    )
    candidate = QuantitativeCandidate(
        field_path="obra.qtd_apartamentos",
        value=value,
        unit="un",
        entity="apartamentos",
        memorial_type=memorial_type,
        source_file=source_file,
        page_number=None,
        source_kind="schematic_apartment_schedule",
        extraction_method="schematic_apartment_ids",
        evidence_text=evidence_text,
        confidence="high",
        is_reference_only=False,
        is_installed_quantity=True,
    )

    current_value = _get_path(context, "obra.qtd_apartamentos")
    if current_value == value:
        return context, [candidate], [], []

    resolved = dict(context)
    _set_path(resolved, "obra.qtd_apartamentos", value)
    resolution = {
        "field_path": "obra.qtd_apartamentos",
        "status": "resolved",
        "selected_value": value,
        "previous_value": current_value,
        "rule": f"{memorial_type}_schematic_apartment_count",
        "message": "Quantidade de apartamentos selecionada pela contagem de APTOs no corte esquematico.",
        "candidates": [candidate.to_report()],
    }
    return resolved, [candidate], [resolution], []


def _is_authoritative_quantitative_evidence(
    *,
    memorial_type: str,
    field_path: str,
    evidence: Any,
) -> bool:
    confidence = str(getattr(evidence, "confidence", "medium"))
    rule = str(getattr(evidence, "rule", ""))
    if confidence == "high":
        return True
    if memorial_type == "gas_natural" and field_path.startswith(
        ("dimensionamento.", "soma.")
    ):
        return confidence in {"high", "medium"}
    if (
        memorial_type == "eletrico"
        and field_path == "gerador.tem_gerador"
        and rule == "generator_mentioned_without_q_board"
    ):
        return True
    return False


def _attach_quantitative_report(
    report: ExtractionReport,
    *,
    candidates: list[QuantitativeCandidate],
    resolutions: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> ExtractionReport:
    if not candidates and not resolutions and not conflicts:
        return report
    cross_validation = dict(report.cross_validation or {})
    cross_validation["quantitative_candidates"] = [
        candidate.to_report() for candidate in candidates
    ]
    cross_validation["quantitative_resolutions"] = resolutions
    cross_validation["quantitative_conflicts"] = conflicts
    return _attach_cross_validation_report(report, cross_validation)


def _apply_authoritative_quantitative_mapper_values(
    context: dict[str, Any],
    mapper_mapping: MappingResult,
    *,
    memorial_type: str,
) -> tuple[dict[str, Any], list[QuantitativeCandidate], list[dict[str, Any]], list[dict[str, Any]]]:
    fields = _AUTHORITATIVE_QUANTITATIVE_FIELDS.get(memorial_type, set())
    if not fields:
        return context, [], [], []

    resolved = dict(context)
    candidates: list[QuantitativeCandidate] = []
    resolutions: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for field_path in fields:
        evidence = mapper_mapping.evidence.get(field_path)
        if evidence is None:
            continue
        mapper_value = getattr(evidence, "value", None)
        if mapper_value is None:
            continue
        candidate = _quantitative_candidate_from_evidence(
            memorial_type=memorial_type,
            field_path=field_path,
            value=mapper_value,
            evidence=evidence,
        )
        candidates.append(candidate)

        if not _is_authoritative_quantitative_evidence(
            memorial_type=memorial_type,
            field_path=field_path,
            evidence=evidence,
        ):
            continue

        current_value = _get_path(resolved, field_path)
        if current_value == mapper_value:
            continue
        _set_path(resolved, field_path, mapper_value)
        resolutions.append(
            {
                "field_path": field_path,
                "status": "resolved",
                "selected_value": mapper_value,
                "previous_value": current_value,
                "rule": f"{memorial_type}_authoritative_mapper_quantitative",
                "message": "Valor quantitativo selecionado a partir de evidencia deterministica do projeto.",
                "candidates": [candidate.to_report()],
            }
        )

    if memorial_type == "eletrico" and _get_path(resolved, "gerador.tem_gerador") is False:
        gerador = resolved.setdefault("gerador", {})
        if isinstance(gerador, dict):
            previous_qtd = gerador.get("qtd")
            previous_power = gerador.get("potencia_kva")
            gerador["qtd"] = 0
            gerador["potencia_kva"] = 0
            if gerador.get("tipo_atendimento") is None:
                gerador["tipo_atendimento"] = "condominio"
            if previous_qtd not in (None, 0) or previous_power not in (None, 0):
                resolutions.append(
                    {
                        "field_path": "gerador",
                        "status": "resolved",
                        "selected_value": {"qtd": 0, "potencia_kva": 0},
                        "previous_value": {
                            "qtd": previous_qtd,
                            "potencia_kva": previous_power,
                        },
                        "rule": "eletrico_generator_absence_zeroes_quantities",
                        "message": "Quantidade e potencia do gerador foram zeradas porque a evidencia indica ausencia de gerador instalado.",
                        "candidates": [],
                    }
                )

    return resolved, candidates, resolutions, conflicts


def _reconcile_gas_natural_quantitative_total(
    context: dict[str, Any],
    *,
    candidates: list[QuantitativeCandidate],
    resolutions: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> dict[str, Any]:
    dimensionamento = context.get("dimensionamento")
    if not isinstance(dimensionamento, dict):
        return context

    values: list[int] = []
    for key in ("qtd_fogao", "qtd_aquecedor", "qtd_churrasqueira"):
        value = dimensionamento.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            return context
        values.append(value)

    calculated_total = sum(values)
    reported_total = _get_path(context, "soma.qtd_pontos_de_utilizacao")
    if reported_total == calculated_total:
        return context

    _set_path(context, "soma.qtd_pontos_de_utilizacao", calculated_total)
    conflicts.append(
        {
            "tipo": "gas_natural_points_total_mismatch",
            "status": "resolved",
            "field_path": "soma.qtd_pontos_de_utilizacao",
            "valores_observados": [reported_total, calculated_total],
            "valor_selecionado": calculated_total,
            "resolucao": "gas_natural_dimensionamento_total_recalculated",
            "mensagem": "Total de pontos recalculado a partir dos pontos individuais.",
        }
    )
    resolutions.append(
        {
            "field_path": "soma.qtd_pontos_de_utilizacao",
            "status": "resolved",
            "selected_value": calculated_total,
            "previous_value": reported_total,
            "rule": "gas_natural_dimensionamento_total_recalculated",
            "message": "Total de pontos recalculado a partir de fogao, aquecedor e churrasqueira.",
            "candidates": [candidate.to_report() for candidate in candidates],
        }
    )
    return context


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

    final_context, candidates, resolutions, conflicts = (
        _apply_authoritative_quantitative_mapper_values(
            final_context,
            mapper_mapping,
            memorial_type="eletrico",
        )
    )
    final_context, ap_candidates, ap_resolutions, ap_conflicts = (
        _apply_schematic_apartment_count_override(
            final_context,
            extraction_result,
            memorial_type="eletrico",
        )
    )
    candidates.extend(ap_candidates)
    resolutions.extend(ap_resolutions)
    conflicts.extend(ap_conflicts)

    mapping = MappingResult(context=final_context, evidence=mapper_mapping.evidence)
    report = assess_extraction_coverage(mapping)
    report = _attach_cross_validation_report(report, llm_result.cross_validation)
    report = _attach_quantitative_report(
        report,
        candidates=candidates,
        resolutions=resolutions,
        conflicts=conflicts,
    )
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
    context, candidates, resolutions, conflicts = _apply_schematic_apartment_count_override(
        mapping.context,
        extraction_result,
        memorial_type="eletrico",
    )
    mapping = MappingResult(context=context, evidence=mapping.evidence)

    mapper_fields = sum(
        len(s) for s in mapping.context.values() if isinstance(s, dict)
    )
    logger.info("Mapper extracted %d fields from %d files", mapper_fields, len(files))

    report = assess_extraction_coverage(mapping)
    report = _attach_quantitative_report(
        report,
        candidates=candidates,
        resolutions=resolutions,
        conflicts=conflicts,
    )
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
        final_context, candidates, resolutions, conflicts = (
            _apply_schematic_apartment_count_override(
                final_context,
                extraction_result,
                memorial_type="telecom",
            )
        )

        mapping = MappingResult(context=final_context, evidence=mapper_mapping.evidence)
        report = assess_telecom_extraction_coverage(mapping)
        report = _attach_cross_validation_report(report, llm_result.cross_validation)
        report = _attach_quantitative_report(
            report,
            candidates=candidates,
            resolutions=resolutions,
            conflicts=conflicts,
        )
        logger.info(
            "Telecom extraction coverage: filled=%d, missing=%d, pending=%d",
            len(report.filled), len(report.missing), len(report.pending),
        )
        return mapping, report

    extraction_result = extract_project_files(files)
    mapping = map_extraction_to_partial_telecom_context(extraction_result)
    context, candidates, resolutions, conflicts = _apply_schematic_apartment_count_override(
        mapping.context,
        extraction_result,
        memorial_type="telecom",
    )
    mapping = MappingResult(context=context, evidence=mapping.evidence)
    report = assess_telecom_extraction_coverage(mapping)
    report = _attach_quantitative_report(
        report,
        candidates=candidates,
        resolutions=resolutions,
        conflicts=conflicts,
    )
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
        final_context, candidates, resolutions, conflicts = (
            _apply_authoritative_quantitative_mapper_values(
                final_context,
                mapper_mapping,
                memorial_type="gas_natural",
            )
        )
        final_context, ap_candidates, ap_resolutions, ap_conflicts = (
            _apply_schematic_apartment_count_override(
                final_context,
                extraction_result,
                memorial_type="gas_natural",
            )
        )
        candidates.extend(ap_candidates)
        resolutions.extend(ap_resolutions)
        conflicts.extend(ap_conflicts)
        final_context = _normalize_gas_natural_context(final_context)
        final_context = _reconcile_gas_natural_quantitative_total(
            final_context,
            candidates=candidates,
            resolutions=resolutions,
            conflicts=conflicts,
        )

        mapping = MappingResult(context=final_context, evidence=mapper_mapping.evidence)
        report = assess_gas_natural_extraction_coverage(mapping)
        report = _attach_cross_validation_report(report, llm_result.cross_validation)
        report = _attach_quantitative_report(
            report,
            candidates=candidates,
            resolutions=resolutions,
            conflicts=conflicts,
        )
        logger.info(
            "Gas natural extraction coverage: filled=%d, missing=%d, pending=%d",
            len(report.filled), len(report.missing), len(report.pending),
        )
        return mapping, report

    extraction_result = extract_project_files(files)
    mapping = map_extraction_to_partial_gas_natural_context(extraction_result)
    context, candidates, resolutions, conflicts = _apply_schematic_apartment_count_override(
        mapping.context,
        extraction_result,
        memorial_type="gas_natural",
    )
    mapping = MappingResult(
        context=_normalize_gas_natural_context(context),
        evidence=mapping.evidence,
    )
    report = assess_gas_natural_extraction_coverage(mapping)
    report = _attach_quantitative_report(
        report,
        candidates=candidates,
        resolutions=resolutions,
        conflicts=conflicts,
    )
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
    final_context, candidates, resolutions, quantitative_conflicts = (
        _apply_schematic_apartment_count_override(
            final_context,
            extraction_result,
            memorial_type="glp",
        )
    )

    final_context = _normalize_glp_non_total_fields(final_context)
    final_context, conflicts = _reconcile_glp_total_points(final_context)
    final_context = _attach_glp_conflicts(final_context, conflicts)

    mapping = MappingResult(context=final_context, evidence=mapper_mapping.evidence)
    report = assess_glp_extraction_coverage(mapping)
    report = _attach_cross_validation_report(report, llm_result.cross_validation)
    report = _attach_quantitative_report(
        report,
        candidates=candidates,
        resolutions=resolutions,
        conflicts=[*quantitative_conflicts, *conflicts],
    )
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
    quantitative_result: GlpV2QuantitativeResult | None = None,
) -> dict[str, Any]:
    work = dict(merged)
    work.pop(_GLP_V2_CRITICAL, None)
    if quantitative_result is None:
        quantitative_result = resolve_glp_v2_quantitatives(work, mapper_critical)

    obra = dict(work.get("obra") or {})
    qtd_ap = quantitative_result.obra.get("qtd_apartamentos")
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
        "quantidade": int(quantitative_result.tanques.get("quantidade") or 0),
        "fonte_evidencia": list(tanques_in.get("fonte_evidencia") or []),
        "conflitos": list(tanques_in.get("conflitos") or []),
    }
    if tanques_in.get("tipo"):
        tanques["tipo"] = tanques_in["tipo"]
    if tanques_in.get("capacidade_kg") is not None:
        tanques["capacidade_kg"] = float(tanques_in["capacidade_kg"])
    if quantitative_result.tanques.get("qtd_abrigos") is not None:
        tanques["qtd_abrigos"] = int(quantitative_result.tanques["qtd_abrigos"])
    elif tanques_in.get("qtd_abrigos") is not None:
        tanques["qtd_abrigos"] = int(tanques_in["qtd_abrigos"])
    if tanques_in.get("qtd_recipientes") is not None:
        tanques["qtd_recipientes"] = int(tanques_in["qtd_recipientes"])

    ab_raw = work.get("abastecimento") or {}
    if not isinstance(ab_raw, dict):
        ab_raw = {}
    pav = ab_raw.get("pavimento")
    abastecimento: dict[str, Any] = {
        "pavimento": str(pav if pav is not None else "térreo"),
    }
    if ab_raw.get("fonte_evidencia"):
        abastecimento["fonte_evidencia"] = ab_raw["fonte_evidencia"]

    dimensionamento = quantitative_result.dimensionamento
    pontos_utilizacao = quantitative_result.pontos_utilizacao

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
    merged = _apply_glp_v2_mapper_overrides(merged, mapper_ctx)

    merged = _normalize_glp_non_total_fields(merged)

    assess_ctx = MappingResult(context=dict(merged), evidence=mapper_mapping.evidence)
    report = assess_glp_v2_extraction_coverage(assess_ctx)
    report = _attach_cross_validation_report(report, llm_result.cross_validation)

    quantitative_candidates = extract_glp_v2_quantitative_candidates(extraction_result)
    quantitative_result = resolve_glp_v2_quantitatives(
        merged,
        critical,
        extra_candidates=quantitative_candidates,
    )
    report = _attach_glp_v2_quantitative_report(report, quantitative_result)
    assembled = _assemble_glp_v2_payload(merged, critical, quantitative_result)
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
