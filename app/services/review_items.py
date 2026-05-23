from __future__ import annotations

from typing import Any

ReviewItem = dict[str, Any]

_CATEGORY_PRIORITY = {
    "conflict": 0,
    "missing": 1,
    "default": 2,
    "low_confidence": 3,
}

_IGNORED_DEFAULT_PATHS = {
    "documento.data_atual",
    "context_version",
    "template_version",
}

_NUMERIC_PATH_FRAGMENTS = (
    "area_",
    "comprimento",
    "diametro",
    "distancia",
    "kva",
    "kw",
    "mm2",
    "potencia",
    "qtd",
    "quantidade",
    "secao",
    "tensao",
    "total",
)


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _get_path(context: dict[str, Any] | None, path: str) -> Any:
    current: Any = context or {}
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _humanize_path(path: str) -> str:
    return path.replace(".", " > ").replace("_", " ").strip().title()


def _editable_type(value: Any, field_path: str) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, (list, dict)):
        return "json"
    normalized_path = field_path.lower()
    leaf = normalized_path.rsplit(".", 1)[-1]
    if leaf.startswith(("tem_", "possui_")):
        return "boolean"
    if any(fragment in normalized_path for fragment in _NUMERIC_PATH_FRAGMENTS):
        return "number"
    return "text"


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "sim" if value else "não"
    if value is None:
        return "vazio"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ", ".join(_format_value(item) for item in value)
    if isinstance(value, dict):
        return ", ".join(
            f"{key}: {_format_value(inner_value)}"
            for key, inner_value in value.items()
        )
    return str(value)


def _corrected_paths(extraction_report: dict[str, Any] | None) -> set[str]:
    if not _is_record(extraction_report):
        return set()
    corrections = extraction_report.get("user_corrections")
    return set(corrections.keys()) if isinstance(corrections, dict) else set()


def _evidence_map(extraction_report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not _is_record(extraction_report):
        return {}
    raw = extraction_report.get("evidence")
    if not isinstance(raw, dict):
        return {}
    return {
        str(path): evidence
        for path, evidence in raw.items()
        if isinstance(evidence, dict)
    }


def _item(
    *,
    category: str,
    field_path: str,
    final_context: dict[str, Any] | None,
    confidence: str | None = None,
    evidence: str | None = None,
    rule: str | None = None,
    current_value: Any = None,
    reason: str | None = None,
) -> ReviewItem:
    value = _get_path(final_context, field_path) if current_value is None else current_value
    return {
        "id": f"{category}:{field_path}",
        "category": category,
        "field_path": field_path,
        "label": _humanize_path(field_path),
        "current_value": value,
        "confidence": confidence,
        "evidence": evidence,
        "rule": rule,
        "reason": reason,
        "editable_type": _editable_type(value, field_path),
    }


def _conflict_field_path(conflict: dict[str, Any], index: int) -> str:
    for key in ("field_path", "path", "campo", "field"):
        value = conflict.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lstrip("$.")
    tipo = str(conflict.get("tipo") or conflict.get("type") or "conflito")
    return f"conflitos.{tipo}.{index}"


def _candidate_files(candidate: dict[str, Any]) -> str:
    files = candidate.get("files") or candidate.get("arquivos") or candidate.get("fontes")
    if not isinstance(files, list):
        return ""
    clean_files = [str(file) for file in files if str(file).strip()]
    return ", ".join(clean_files[:3])


def _candidate_summary(candidate: dict[str, Any]) -> str:
    value = _format_value(candidate.get("value", candidate.get("valor")))
    occurrence_count = candidate.get("occurrence_count") or candidate.get("ocorrencias")
    suffixes: list[str] = []
    if isinstance(occurrence_count, int):
        suffixes.append(
            f"{occurrence_count} ocorrência"
            if occurrence_count == 1
            else f"{occurrence_count} ocorrências"
        )
    files = _candidate_files(candidate)
    if files:
        suffixes.append(files)
    if not suffixes:
        return value
    return f"{value} ({', '.join(suffixes)})"


def _format_conflict_evidence(conflict: dict[str, Any]) -> str:
    parts: list[str] = []
    message = conflict.get("mensagem") or conflict.get("message")
    if isinstance(message, str) and message.strip():
        parts.append(message.strip())

    candidates = [
        candidate
        for candidate in _as_list(conflict.get("candidates"))
        if isinstance(candidate, dict)
    ]
    if candidates:
        parts.append(
            "Valores encontrados: "
            + "; ".join(_candidate_summary(candidate) for candidate in candidates)
            + "."
        )
    else:
        observed = conflict.get("valores_observados") or conflict.get("observed_values")
        if isinstance(observed, list) and observed:
            parts.append(
                "Valores encontrados: "
                + " e ".join(_format_value(value) for value in observed)
                + "."
            )

    selected = conflict.get("valor_selecionado", conflict.get("selected_value"))
    if selected is not None:
        parts.append(f"Valor selecionado automaticamente: {_format_value(selected)}.")
    elif str(conflict.get("status") or "").startswith("unresolved"):
        parts.append("Sem regra segura para escolher automaticamente.")

    return " ".join(parts)


def _conflict_reason(conflict: dict[str, Any]) -> str:
    status = str(conflict.get("status") or "")
    if status.startswith("unresolved"):
        return (
            "Foram encontrados valores diferentes para este campo e não houve critério "
            "seguro para escolher automaticamente. Informe o valor correto conforme o projeto."
        )
    return (
        "Foi encontrada uma divergência na extração e o sistema aplicou uma regra de "
        "resolução. Confira se o valor selecionado está coerente com o projeto."
    )


def _iter_conflicts(extraction_report: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not _is_record(extraction_report):
        return []
    conflicts: list[dict[str, Any]] = []
    for conflict in _as_list(extraction_report.get("conflicts")):
        if isinstance(conflict, dict):
            conflicts.append(conflict)
    cross_validation = extraction_report.get("cross_validation")
    if isinstance(cross_validation, dict):
        for key in ("conflicts", "quantitative_conflicts"):
            for conflict in _as_list(cross_validation.get(key)):
                if isinstance(conflict, dict):
                    conflicts.append(conflict)
    return conflicts


def _is_default_evidence(evidence: dict[str, Any]) -> bool:
    rule = str(evidence.get("rule") or "").lower()
    text = str(evidence.get("evidence") or "").lower()
    return "default" in rule or "default" in text or "valor padrão" in text


def build_review_items(
    final_context: dict[str, Any] | None,
    extraction_report: dict[str, Any] | None,
) -> list[ReviewItem]:
    """Build editable quality issues for any memorial type.

    The backend owns this classification because confidence, defaults and
    extraction rules are technical details from the extraction pipeline.
    """
    if not isinstance(final_context, dict) and not isinstance(extraction_report, dict):
        return []

    report = extraction_report if isinstance(extraction_report, dict) else {}
    corrected = _corrected_paths(report)
    items_by_path: dict[str, ReviewItem] = {}

    def add(item: ReviewItem) -> None:
        path = str(item["field_path"])
        if path in corrected:
            return
        previous = items_by_path.get(path)
        if previous is None or (
            _CATEGORY_PRIORITY[item["category"]] < _CATEGORY_PRIORITY[previous["category"]]
        ):
            items_by_path[path] = item

    for index, conflict in enumerate(_iter_conflicts(report)):
        path = _conflict_field_path(conflict, index)
        add(
            _item(
                category="conflict",
                field_path=path,
                final_context=final_context,
                confidence="low",
                evidence=_format_conflict_evidence(conflict),
                reason=_conflict_reason(conflict),
            )
        )

    for path in _as_list(report.get("missing")) + _as_list(report.get("pending")):
        if isinstance(path, str) and path.strip():
            normalized_path = path.strip().lstrip("$.")
            add(
                _item(
                    category="missing",
                    field_path=normalized_path,
                    final_context=final_context,
                    confidence="low",
                    reason="Campo não encontrado com segurança nas pranchas.",
                )
            )

    for path, evidence in _evidence_map(report).items():
        if path in _IGNORED_DEFAULT_PATHS:
            continue
        confidence = str(evidence.get("confidence") or "medium").lower()
        category = "default" if _is_default_evidence(evidence) else None
        if category is None and confidence in {"low", "medium"}:
            category = "low_confidence"
        if category is None:
            continue
        add(
            _item(
                category=category,
                field_path=path,
                final_context=final_context,
                confidence=confidence,
                evidence=evidence.get("evidence")
                if isinstance(evidence.get("evidence"), str)
                else None,
                rule=evidence.get("rule") if isinstance(evidence.get("rule"), str) else None,
                current_value=evidence.get("value", _get_path(final_context, path)),
                reason=(
                    "Valor preenchido por regra padrão."
                    if category == "default"
                    else "Valor extraído sem confiança alta."
                ),
            )
        )

    return sorted(
        items_by_path.values(),
        key=lambda item: (
            _CATEGORY_PRIORITY.get(str(item.get("category")), 99),
            str(item.get("field_path", "")),
        ),
    )
