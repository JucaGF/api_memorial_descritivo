from __future__ import annotations

import re
from typing import Any

from app.services.project_extractor import ProjectExtractionResult


ATERRAMENTO_SYSTEMS = ("TN-C-S", "TN-S", "TN-C", "TT", "IT")


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_labeled_value(raw_text: str, labels: list[str]) -> str | None:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    for line in lines:
        for label in labels:
            pattern = re.compile(rf"^{label}\s*[:\-]\s*(.+)$", re.IGNORECASE)
            match = pattern.search(line)
            if match:
                value = match.group(1).strip(" .;-")
                if value:
                    return value
    return None


def _extract_numeric_value(patterns: list[str], text: str) -> float | int | None:
    for raw_pattern in patterns:
        match = re.search(raw_pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        value = match.group(1).replace(",", ".")
        number = float(value)
        if number.is_integer():
            return int(number)
        return number
    return None


def _extract_construtora(raw_text: str) -> str | None:
    return _extract_labeled_value(
        raw_text,
        labels=[
            r"construtora",
            r"empresa construtora",
            r"respons[áa]vel pela obra",
        ],
    )


def _extract_nome_obra(raw_text: str) -> str | None:
    return _extract_labeled_value(
        raw_text,
        labels=[
            r"nome da obra",
            r"obra",
            r"empreendimento",
            r"edif[íi]cio",
        ],
    )


def _extract_localizacao(raw_text: str) -> str | None:
    return _extract_labeled_value(
        raw_text,
        labels=[
            r"localiza[çc][ãa]o",
            r"endere[çc]o",
            r"local da obra",
        ],
    )


def _extract_tem_subestacao(text: str) -> bool | None:
    lowered_text = text.lower()
    negative_patterns = (
        "sem subestacao",
        "sem subestação",
        "nao possui subestacao",
        "não possui subestação",
        "dispensa de subestacao",
        "dispensa de subestação",
    )
    if any(pattern in lowered_text for pattern in negative_patterns):
        return False

    positive_patterns = (
        "subestacao",
        "subestação",
        "cabine primaria",
        "cabine primária",
    )
    if any(pattern in lowered_text for pattern in positive_patterns):
        return True
    return None


def _extract_tipo_subestacao(raw_text: str, tem_subestacao: bool | None) -> str | None:
    if tem_subestacao is not True:
        return None

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    positive_markers = ("abrigada", "aérea", "aerea", "simplificada", "blindada", "abaixadora")
    negative_markers = ("sem subestação", "sem subestacao", "não possui subestação", "nao possui subestacao")

    for line in lines:
        lowered_line = line.lower()
        if "subestação" not in lowered_line and "subestacao" not in lowered_line:
            continue
        if any(marker in lowered_line for marker in negative_markers):
            continue
        if any(marker in lowered_line for marker in positive_markers):
            cleaned_line = line.strip(" .;-")
            if cleaned_line:
                return cleaned_line

    match = re.search(
        r"(subesta[çc][ãa]o[^.:\n]{0,80})",
        raw_text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1).strip(" .;-")
    return None


def _extract_aterramento_tipo_sistema(text: str) -> str | None:
    for system in ATERRAMENTO_SYSTEMS:
        if re.search(rf"\b{re.escape(system)}\b", text, flags=re.IGNORECASE):
            return system
    return None


def _extract_mt_tensao_kv(text: str) -> float | int | None:
    return _extract_numeric_value(
        patterns=[
            r"m[ée]dia tens[ãa]o[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*kV\b",
            r"tens[ãa]o[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*kV\b",
            r"\b(\d+(?:[.,]\d+)?)\s*kV\b",
        ],
        text=text,
    )


def _extract_mt_secao_cabo_mm2(text: str) -> float | int | None:
    return _extract_numeric_value(
        patterns=[
            r"se[cç][aã]o(?:\s+do)?\s+cabo[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*mm2\b",
            r"cabo[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*mm2\b",
            r"(\d+(?:[.,]\d+)?)\s*mm2\b",
        ],
        text=text,
    )


def map_extraction_to_partial_context(
    extraction_result: ProjectExtractionResult,
) -> dict[str, Any]:
    raw_text = extraction_result.raw_text
    text = _normalize_text(raw_text)
    tem_subestacao = _extract_tem_subestacao(text)

    return {
        "obra": {
            "construtora": _extract_construtora(raw_text),
            "nome": _extract_nome_obra(raw_text),
            "localizacao": _extract_localizacao(raw_text),
        },
        "energia": {
            "tem_subestacao": tem_subestacao,
            "tipo_subestacao": _extract_tipo_subestacao(raw_text, tem_subestacao),
        },
        "aterramento": {
            "tipo_sistema": _extract_aterramento_tipo_sistema(text),
        },
        "mt": {
            "tensao_kv": _extract_mt_tensao_kv(text),
            "secao_cabo_mm2": _extract_mt_secao_cabo_mm2(text),
        },
    }
