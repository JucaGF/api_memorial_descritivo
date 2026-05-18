from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class QuantitativeCandidate:
    field_path: str
    value: int | float | str
    unit: str | None
    entity: str
    memorial_type: str
    source_file: str | None
    page_number: int | None
    source_kind: str
    extraction_method: str
    evidence_text: str | None
    confidence: str
    scope: dict[str, Any] = field(default_factory=dict)
    is_reference_only: bool = False
    is_installed_quantity: bool = True

    @property
    def normalized_key(self) -> str:
        return json.dumps(
            {
                "field_path": self.field_path,
                "value": self.value,
                "unit": self.unit,
                "entity": self.entity,
                "scope": self.scope,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def to_report(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["normalized_key"] = self.normalized_key
        return payload


@dataclass(frozen=True)
class GlpV2QuantitativeResult:
    obra: dict[str, Any]
    tanques: dict[str, Any]
    dimensionamento: dict[str, int]
    pontos_utilizacao: dict[str, Any]
    conflicts: list[dict[str, Any]]
    resolutions: list[dict[str, Any]]
    candidates: list[QuantitativeCandidate]

    def to_cross_validation_payload(self) -> dict[str, Any]:
        return {
            "quantitative_candidates": [candidate.to_report() for candidate in self.candidates],
            "quantitative_resolutions": self.resolutions,
            "quantitative_conflicts": self.conflicts,
        }


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    return int(value)


def _candidate(
    *,
    field_path: str,
    value: int | float | str,
    entity: str,
    source_kind: str,
    extraction_method: str,
    confidence: str = "medium",
    evidence_text: str | None = None,
    unit: str | None = None,
    scope: dict[str, Any] | None = None,
    is_reference_only: bool = False,
) -> QuantitativeCandidate:
    return QuantitativeCandidate(
        field_path=field_path,
        value=value,
        unit=unit,
        entity=entity,
        memorial_type="glp_v2",
        source_file=None,
        page_number=None,
        source_kind=source_kind,
        extraction_method=extraction_method,
        evidence_text=evidence_text,
        confidence=confidence,
        scope=scope or {},
        is_reference_only=is_reference_only,
        is_installed_quantity=not is_reference_only,
    )


def _ascii_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _glp_v2_repeated_floor_multiplier(text: str) -> int | None:
    match = re.search(
        r"\(\s*(\d+)\s*PAV\s+X\s+\d+\s*APTOS?\s*\[\s*02\s*PONTOS\s*\]\s*=\s*\d+\s*PONTOS\s*\)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return int(match.group(1))


def _glp_v2_is_upper_floor_source(filename: str, text: str) -> bool:
    key = _ascii_key(f"{filename} {text[:500]}")
    if any(marker in key for marker in ("terreo", "subsolo", "corte", "detalhe", "legenda")):
        return False
    return "pavimento" in key and bool(re.search(r"\b\d+\s*(?:o|e|ao)\b", key))


def _glp_v2_appliance_label_count(text: str, appliance: str) -> int:
    if appliance == "fogao":
        pattern = r"\bfog(?:ão|oes|ões)\s+7[,.]000\b"
    else:
        pattern = r"\bchurrasqueiras?\s+7[,.]000\b"
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def extract_glp_v2_quantitative_candidates(extraction_result: Any) -> list[QuantitativeCandidate]:
    """Extract deterministic GLP v2 quantitative candidates from project text.

    The candidates are intentionally not final values. They become auditable
    evidence for the resolver, which can prefer installed quantities over weak
    LLM totals while still surfacing conflicts.
    """

    source_files = list(getattr(extraction_result, "source_files", []) or [])
    contributions: dict[str, list[tuple[int, str, str | None]]] = {
        "fogao": [],
        "churrasqueira": [],
    }

    for source_file in source_files:
        text = str(getattr(source_file, "extracted_text", "") or "")
        filename = str(getattr(source_file, "original_filename", "") or "")
        if not text:
            continue

        multiplier = _glp_v2_repeated_floor_multiplier(text)
        is_upper_floor = _glp_v2_is_upper_floor_source(filename, text)
        if multiplier is None and not is_upper_floor:
            continue

        for entity in ("fogao", "churrasqueira"):
            count = _glp_v2_appliance_label_count(text, entity)
            if count <= 0:
                continue
            contribution = count * multiplier if multiplier is not None else count
            scope = (
                f"{count} rotulos x {multiplier} pavimentos"
                if multiplier is not None
                else f"{count} rotulos em pavimento identificado"
            )
            contributions[entity].append((contribution, scope, filename or None))

    candidates: list[QuantitativeCandidate] = []
    for entity, field_path in (
        ("fogao", "pontos_utilizacao.fogao"),
        ("churrasqueira", "pontos_utilizacao.churrasqueira"),
    ):
        parts = contributions[entity]
        if not parts:
            continue
        value = sum(part[0] for part in parts)
        candidates.append(
            QuantitativeCandidate(
                field_path=field_path,
                value=value,
                unit="un",
                entity=entity,
                memorial_type="glp_v2",
                source_file=None,
                page_number=None,
                source_kind="deterministic_installed_quantity",
                extraction_method="glp_v2_appliance_labels_with_floor_scope",
                evidence_text="; ".join(part[1] for part in parts),
                confidence="high",
                scope={
                    "parts": [
                        {"value": part[0], "evidence": part[1], "source_file": part[2]}
                        for part in parts
                    ]
                },
            )
        )

    if {"fogao", "churrasqueira"} <= {
        candidate.entity for candidate in candidates
    }:
        total = sum(int(candidate.value) for candidate in candidates)
        candidates.append(
            QuantitativeCandidate(
                field_path="pontos_utilizacao.total_calculado",
                value=total,
                unit="un",
                entity="pontos_utilizacao_total",
                memorial_type="glp_v2",
                source_file=None,
                page_number=None,
                source_kind="deterministic_installed_quantity",
                extraction_method="glp_v2_sum_authoritative_appliance_candidates",
                evidence_text="soma dos candidatos determinísticos de fogão e churrasqueira",
                confidence="high",
            )
        )

    return candidates


def _append_int_candidate(
    candidates: list[QuantitativeCandidate],
    *,
    field_path: str,
    value: Any,
    entity: str,
    source_kind: str,
    extraction_method: str,
) -> None:
    if value is None or isinstance(value, bool):
        return
    candidates.append(
        _candidate(
            field_path=field_path,
            value=int(value),
            entity=entity,
            source_kind=source_kind,
            extraction_method=extraction_method,
        )
    )


def _glp_v2_points_candidates(
    dimensionamento: dict[str, Any],
    pontos_utilizacao: dict[str, Any],
) -> list[QuantitativeCandidate]:
    candidates: list[QuantitativeCandidate] = []
    field_specs = (
        ("qtd_fogao", "fogao", "fogao"),
        ("qtd_churrasqueira", "churrasqueira", "churrasqueira"),
        ("qtd_aquecedor", "aquecedor", "aquecedor"),
        ("qtd_outros", "outros", "outros"),
    )
    for dim_key, pontos_key, entity in field_specs:
        _append_int_candidate(
            candidates,
            field_path=f"dimensionamento.{dim_key}",
            value=dimensionamento.get(dim_key),
            entity=entity,
            source_kind="merged_context",
            extraction_method="llm_or_mapper",
        )
        _append_int_candidate(
            candidates,
            field_path=f"pontos_utilizacao.{pontos_key}",
            value=pontos_utilizacao.get(pontos_key),
            entity=entity,
            source_kind="merged_context",
            extraction_method="llm_or_mapper",
        )
    _append_int_candidate(
        candidates,
        field_path="pontos_utilizacao.total_extraido",
        value=pontos_utilizacao.get("total_extraido"),
        entity="pontos_utilizacao_total",
        source_kind="quantitative_table_or_explicit_total",
        extraction_method="llm_or_mapper",
    )
    return candidates


def _copy_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _resolve_scalar_quantity(
    *,
    field_path: str,
    raw_value: Any,
    entity: str,
    source_kind: str,
    extraction_method: str,
    candidates: list[QuantitativeCandidate],
    resolutions: list[dict[str, Any]],
    default: int = 0,
) -> int:
    value = raw_value.get("valor") if isinstance(raw_value, dict) else raw_value
    selected = _as_int(value, default)
    candidate = _candidate(
        field_path=field_path,
        value=selected,
        entity=entity,
        source_kind=source_kind,
        extraction_method=extraction_method,
        confidence=(
            str(raw_value.get("confianca") or "medium")
            if isinstance(raw_value, dict)
            else "medium"
        ),
        evidence_text=None,
    )
    candidates.append(candidate)
    resolutions.append(
        _resolution_report(
            field_path=field_path,
            status="resolved",
            selected_value=selected,
            rule="glp_v2_single_candidate_quantity",
            message="Valor quantitativo selecionado a partir do contexto extraido.",
            candidates=[candidate],
        )
    )
    return selected


def _resolution_report(
    *,
    field_path: str,
    status: str,
    selected_value: Any,
    rule: str,
    message: str,
    candidates: list[QuantitativeCandidate],
) -> dict[str, Any]:
    return {
        "field_path": field_path,
        "status": status,
        "selected_value": selected_value,
        "rule": rule,
        "message": message,
        "candidates": [candidate.to_report() for candidate in candidates],
    }


_AUTHORITATIVE_SOURCE_PRIORITY = {
    "installed_quantity_table": 100,
    "deterministic_installed_quantity": 95,
    "visual_installed_labels": 90,
    "schematic_installed_labels": 80,
    "unit_schedule": 75,
}
_CONFIDENCE_PRIORITY = {"high": 3, "medium": 2, "low": 1}


def _candidate_priority(candidate: QuantitativeCandidate) -> tuple[int, int]:
    return (
        _AUTHORITATIVE_SOURCE_PRIORITY.get(candidate.source_kind, 0),
        _CONFIDENCE_PRIORITY.get(candidate.confidence, 0),
    )


def _select_authoritative_int_candidate(
    candidates: list[QuantitativeCandidate],
    *,
    field_paths: set[str],
    entity: str,
) -> QuantitativeCandidate | None:
    eligible: list[QuantitativeCandidate] = []
    for candidate in candidates:
        if candidate.field_path not in field_paths and candidate.entity != entity:
            continue
        if candidate.is_reference_only or not candidate.is_installed_quantity:
            continue
        if not isinstance(candidate.value, int) or isinstance(candidate.value, bool):
            continue
        source_priority, _confidence_priority = _candidate_priority(candidate)
        if source_priority <= 0:
            continue
        eligible.append(candidate)
    if not eligible:
        return None

    eligible.sort(key=_candidate_priority, reverse=True)
    best = eligible[0]
    best_priority = _candidate_priority(best)
    same_strength = [
        candidate for candidate in eligible
        if _candidate_priority(candidate) == best_priority
    ]
    values = {candidate.value for candidate in same_strength}
    if len(values) > 1:
        return None
    return best


def resolve_glp_v2_quantitatives(
    merged: dict[str, Any],
    mapper_critical: list[dict[str, Any]],
    *,
    extra_candidates: list[QuantitativeCandidate] | None = None,
) -> GlpV2QuantitativeResult:
    """Resolve GLP v2 quantitative fields before final schema rendering.

    This keeps the final memorial deterministic: LLM/mapper output becomes
    candidates, while this resolver decides or reports conflicts.
    """

    obra_in = merged.get("obra") if isinstance(merged.get("obra"), dict) else {}
    tanques_in = merged.get("tanques") if isinstance(merged.get("tanques"), dict) else {}
    obra = _copy_dict(obra_in)
    tanques = _copy_dict(tanques_in)
    dimensionamento_in = (
        merged.get("dimensionamento")
        if isinstance(merged.get("dimensionamento"), dict)
        else {}
    )
    pontos_in = (
        merged.get("pontos_utilizacao")
        if isinstance(merged.get("pontos_utilizacao"), dict)
        else {}
    )

    dimensionamento = {
        "qtd_fogao": _as_int(dimensionamento_in.get("qtd_fogao")),
        "qtd_aquecedor": _as_int(dimensionamento_in.get("qtd_aquecedor")),
        "qtd_churrasqueira": _as_int(dimensionamento_in.get("qtd_churrasqueira")),
        "qtd_outros": _as_int(dimensionamento_in.get("qtd_outros")),
    }

    fog_i = _as_int(pontos_in.get("fogao"), dimensionamento["qtd_fogao"])
    ch_i = _as_int(pontos_in.get("churrasqueira"), dimensionamento["qtd_churrasqueira"])
    aq_i = _as_int(pontos_in.get("aquecedor"), dimensionamento["qtd_aquecedor"])
    ou_i = _as_int(pontos_in.get("outros"), dimensionamento["qtd_outros"])
    candidates = _glp_v2_points_candidates(dimensionamento_in, pontos_in)
    candidates.extend(extra_candidates or [])
    conflicts: list[dict[str, Any]] = [
        dict(c) for c in (pontos_in.get("conflitos") or []) if isinstance(c, dict)
    ]
    resolutions: list[dict[str, Any]] = []

    authoritative_point_fields: set[str] = set()
    point_specs = (
        (
            "pontos_utilizacao.fogao",
            "dimensionamento.qtd_fogao",
            "fogao",
            "qtd_fogao",
            "fogao",
        ),
        (
            "pontos_utilizacao.churrasqueira",
            "dimensionamento.qtd_churrasqueira",
            "churrasqueira",
            "qtd_churrasqueira",
            "churrasqueira",
        ),
        (
            "pontos_utilizacao.aquecedor",
            "dimensionamento.qtd_aquecedor",
            "aquecedor",
            "qtd_aquecedor",
            "aquecedor",
        ),
        (
            "pontos_utilizacao.outros",
            "dimensionamento.qtd_outros",
            "outros",
            "qtd_outros",
            "outros",
        ),
    )
    selected_point_values = {
        "fogao": fog_i,
        "churrasqueira": ch_i,
        "aquecedor": aq_i,
        "outros": ou_i,
    }
    for pontos_path, dimensionamento_path, pontos_key, dimensionamento_key, entity in point_specs:
        selected = _select_authoritative_int_candidate(
            candidates,
            field_paths={pontos_path, dimensionamento_path},
            entity=entity,
        )
        if selected is None:
            continue
        selected_point_values[pontos_key] = int(selected.value)
        dimensionamento[dimensionamento_key] = int(selected.value)
        authoritative_point_fields.add(pontos_key)
        resolutions.append(
            _resolution_report(
                field_path=pontos_path,
                status="resolved",
                selected_value=selected.value,
                rule="glp_v2_authoritative_quantitative_candidate",
                message="Valor selecionado a partir de candidato quantitativo instalado com evidencia mais forte.",
                candidates=[selected],
            )
        )

    fog_i = selected_point_values["fogao"]
    ch_i = selected_point_values["churrasqueira"]
    aq_i = selected_point_values["aquecedor"]
    ou_i = selected_point_values["outros"]
    total_calc = fog_i + ch_i + aq_i + ou_i

    qtd_apartamentos = _resolve_scalar_quantity(
        field_path="obra.qtd_apartamentos.valor",
        raw_value=obra.get("qtd_apartamentos"),
        entity="apartamentos",
        source_kind="unit_schedule_or_project_metadata",
        extraction_method="llm_or_mapper",
        candidates=candidates,
        resolutions=resolutions,
        default=0,
    )
    qtd_tanques = _resolve_scalar_quantity(
        field_path="tanques.quantidade",
        raw_value=tanques.get("quantidade"),
        entity="tanques_glp_instalados",
        source_kind="shelter_or_tank_drawing",
        extraction_method="llm_or_mapper",
        candidates=candidates,
        resolutions=resolutions,
        default=0,
    )
    obra["qtd_apartamentos"] = qtd_apartamentos
    tanques["quantidade"] = qtd_tanques

    for mapper_conflict in mapper_critical:
        if (
            mapper_conflict.get("tipo") == "glp_v2_fogao_apartamentos_colision"
            and fog_i != qtd_apartamentos
        ):
            continue
        conflicts.append(dict(mapper_conflict))

    total_ext = pontos_in.get("total_extraido")
    if total_ext is not None and int(total_ext) != total_calc:
        total_ext_i = int(total_ext)
        if {"fogao", "churrasqueira"}.issubset(authoritative_point_fields):
            conflicts.append(
                {
                    "tipo": "glp_v2_points_total_mismatch",
                    "status": "resolved",
                    "valores_observados": [total_ext_i, total_calc],
                    "valor_selecionado": total_calc,
                    "fontes": ["total_extraido", "pontos_individuais"],
                    "resolucao": "glp_v2_authoritative_individual_points",
                    "mensagem": (
                        "Total extraido diverge dos pontos individuais, mas os pontos por tipo "
                        "vieram de evidencias instaladas mais fortes; total final foi recalculado."
                    ),
                }
            )
            resolutions.append(
                _resolution_report(
                    field_path="pontos_utilizacao.total_calculado",
                    status="resolved",
                    selected_value=total_calc,
                    rule="glp_v2_authoritative_individual_points",
                    message="Total recalculado a partir de pontos individuais com evidencia instalada.",
                    candidates=[
                        candidate for candidate in candidates
                        if candidate.entity in {"fogao", "churrasqueira"}
                    ],
                )
            )
        elif (
            total_ext_i > 0
            and total_ext_i % 2 == 0
            and fog_i > 0
            and ch_i > 0
            and aq_i == 0
            and ou_i == 0
        ):
            previous_total = total_calc
            fog_i = total_ext_i // 2
            ch_i = total_ext_i // 2
            total_calc = fog_i + ch_i + aq_i + ou_i
            dimensionamento["qtd_fogao"] = fog_i
            dimensionamento["qtd_churrasqueira"] = ch_i
            conflicts.append(
                {
                    "tipo": "glp_v2_points_total_mismatch",
                    "status": "resolved",
                    "valores_observados": [total_ext_i, previous_total],
                    "valor_selecionado": total_calc,
                    "fontes": ["total_extraido", "total_calculado"],
                    "resolucao": "glp_v2_even_total_split",
                    "mensagem": (
                        "Total extraido difere da soma por tipo; como apenas fogao e churrasqueira "
                        "aparecem como pontos positivos, o total par foi dividido igualmente."
                    ),
                }
            )
            resolutions.append(
                _resolution_report(
                    field_path="pontos_utilizacao.total_calculado",
                    status="resolved",
                    selected_value=total_calc,
                    rule="glp_v2_even_total_split",
                    message=(
                        "Total extraido par foi reconciliado dividindo igualmente entre fogao "
                        "e churrasqueira porque aquecedor/outros estavam zerados."
                    ),
                    candidates=candidates,
                )
            )
        else:
            conflicts.append(
                {
                    "tipo": "glp_v2_points_total_mismatch",
                    "status": "unresolved",
                    "valores_observados": [total_ext, total_calc],
                    "fontes": ["total_extraido", "total_calculado"],
                    "mensagem": "Total extraido difere da soma por tipo.",
                }
            )
            resolutions.append(
                _resolution_report(
                    field_path="pontos_utilizacao.total_calculado",
                    status="unresolved",
                    selected_value=None,
                    rule="glp_v2_total_mismatch_requires_review",
                    message="Total extraido difere da soma por tipo e nao ha regra segura para resolver.",
                    candidates=candidates,
                )
            )

    pontos_utilizacao = {
        "fogao": fog_i,
        "churrasqueira": ch_i,
        "aquecedor": aq_i,
        "outros": ou_i,
        "total_extraido": total_ext,
        "total_calculado": total_calc,
        "fontes_evidencia": list(pontos_in.get("fontes_evidencia") or []),
        "conflitos": conflicts,
    }

    return GlpV2QuantitativeResult(
        obra=obra,
        tanques=tanques,
        dimensionamento=dimensionamento,
        pontos_utilizacao=pontos_utilizacao,
        conflicts=conflicts,
        resolutions=resolutions,
        candidates=candidates,
    )
