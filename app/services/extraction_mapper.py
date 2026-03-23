from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.project_extractor import ProjectExtractionResult


ATERRAMENTO_SYSTEMS = ("TN-C-S", "TN-S", "TN-C", "TT", "IT")

# Campos que o mapper atual tenta extrair do texto dos projetos.
EXTRACTABLE_BY_MAPPER = (
    "obra.construtora",
    "obra.nome",
    "obra.localizacao",
    "obra.numero_cadastro",
    "obra.qtd_apartamentos",
    "energia.tem_subestacao",
    "energia.tipo_subestacao",
    "aterramento.tipo_sistema",
    "aterramento.qtd_hastes",
    "aterramento.secao_cabo_cobre_mm2",
    "mt.tensao_kv",
    "mt.secao_cabo_mm2",
    "instalacao.perfilado_tipo",
    "gerador.tipo_atendimento",
    "nao_inclusos.cpct",
    "nao_inclusos.cftv",
    "nao_inclusos.alarme_patrimonial",
    "nao_inclusos.sonorizacao",
    "nao_inclusos.alarme_incendio",
    "nao_inclusos.automacao",
)

# Campos extraíveis identificados nos projetos reais, ainda não implementados.
PENDING_EXTRACTION = (
    "obra.tipo_edificacao",
    "obra.tipologia",
    "obra.qtd_lojas",
    "obra.qtd_restaurantes",
    "aterramento.secao_cabo_malha_mm2",
    "aterramento.local_bep",
    "gerador.qtd",
    "gerador.potencia_kva",
)


@dataclass(frozen=True)
class FieldExtraction:
    value: Any
    rule: str
    evidence: str | None = None
    confidence: str = "medium"  # "high" | "medium" | "low"


@dataclass(frozen=True)
class ExtractionReport:
    filled: list[str]
    missing: list[str]
    pending: list[str]
    evidence: dict[str, FieldExtraction] = field(default_factory=dict)


@dataclass(frozen=True)
class MappingResult:
    context: dict[str, Any]
    evidence: dict[str, FieldExtraction]


# ── Padrões compilados ────────────────────────────────────────────────────────

_COMPANY_PATTERN = re.compile(
    r"\b(?:LTDA\.?|S\.A\.|EIRELI|CONSTRU[ÇC][ÃA]O|INCORPORA[ÇC][ÃA]O|EMPREENDIMENTOS|ENGENHARIA)\b",
    re.IGNORECASE,
)
_ADDRESS_PATTERN = re.compile(
    r"\b(?:AV\.|AVENIDA|RUA|AL\.|ESTRADA|RODOVIA|TRAVESSA|LOTEAMENTO)\b",
    re.IGNORECASE,
)

# Labels de quadros especializados. Presença → sistema incluído (False).
# Ausência → sistema não incluso (True).
_CIRCUIT_LABELS: dict[str, list[str]] = {
    "cftv": [r"Q[.\-]CFTV", r"\bCFTV\b"],
    "alarme_incendio": [r"Q[.\-]INC(?:ENDIO)?", r"ALARME\s+DE\s+INC[EÊ]NDIO", r"SISTEMA\s+DE\s+INC[EÊ]NDIO"],
    "alarme_patrimonial": [r"Q[.\-]ALARM(?:E)?", r"\bALARME\s+PATRIMONIAL\b"],
    "sonorizacao": [r"Q[.\-]SOM", r"SONORIZA[CÇ][ÃA]O"],
    "automacao": [r"Q[.\-]AUTO", r"AUTOMA[CÇ][ÃA]O\s+PREDIAL"],
    "cpct": [r"Q[.\-]CPCT", r"\bCPCT\b"],
}

_GENERATOR_BOARD_RE = re.compile(
    r"Q[.\-](?:GER(?:ADOR)?|GEN)[^\n]{0,150}",
    re.IGNORECASE,
)


# ── Helpers primitivos ────────────────────────────────────────────────────────

def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _looks_like_building_name(text: str) -> bool:
    if not text or len(text) > 60:
        return False
    if re.search(r"\d{2}/\d{2,4}", text):
        return False
    if re.match(r"^[A-Z]-\d+", text):
        return False
    if re.search(r"\bPROJETO\b", text, re.IGNORECASE):
        return False
    if _COMPANY_PATTERN.search(text):
        return False
    return True


def _find_company_line(raw_text: str) -> tuple[int, list[str]] | None:
    """Encontra a primeira linha com padrão de razão social no bloco do carimbo."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if _COMPANY_PATTERN.search(line) and len(line) > 10:
            return i, lines
    return None


def _extract_labeled_value(raw_text: str, labels: list[str]) -> tuple[str, str] | None:
    """Retorna (valor, linha_evidência) ou None."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        for label in labels:
            pattern = re.compile(rf"^{label}\s*[:\-]\s*(.+)$", re.IGNORECASE)
            match = pattern.search(line)
            if match:
                value = match.group(1).strip(" .;-")
                if value:
                    return value, line
            label_only = re.compile(rf"^{label}\s*[:\-]?\s*$", re.IGNORECASE)
            if label_only.match(line) and i + 1 < len(lines):
                value = lines[i + 1].strip(" .;-")
                if value:
                    return value, f"{line} → {value}"
    return None


def _extract_numeric_value(patterns: list[str], text: str) -> tuple[float | int, str] | None:
    """Retorna (número, trecho_evidência) ou None."""
    for raw_pattern in patterns:
        match = re.search(raw_pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        number = float(match.group(1).replace(",", "."))
        number = int(number) if number.is_integer() else number
        start = max(0, match.start() - 10)
        end = min(len(text), match.end() + 10)
        return number, text[start:end].strip()
    return None


def _add_field(
    context: dict[str, Any],
    evidence: dict[str, FieldExtraction],
    path: str,
    extraction: FieldExtraction | None,
) -> None:
    if extraction is None:
        return
    keys = path.split(".")
    target = context
    for key in keys[:-1]:
        if key not in target:
            target[key] = {}
        target = target[key]
    target[keys[-1]] = extraction.value
    evidence[path] = extraction


# ── Extratores individuais ────────────────────────────────────────────────────

def _extract_construtora(raw_text: str) -> FieldExtraction | None:
    result = _find_company_line(raw_text)
    if result:
        i, lines = result
        return FieldExtraction(
            value=lines[i],
            evidence=lines[i],
            rule="carimbo_company_pattern",
            confidence="high",
        )
    labeled = _extract_labeled_value(
        raw_text,
        labels=[r"construtora", r"empresa construtora", r"respons[áa]vel pela obra", "construtor"],
    )
    if labeled:
        value, evidence = labeled
        return FieldExtraction(value=value, evidence=evidence, rule="labeled_value", confidence="medium")
    return None


def _extract_nome_obra(raw_text: str) -> FieldExtraction | None:
    result = _find_company_line(raw_text)
    if result:
        i, lines = result
        if i > 0:
            candidate = lines[i - 1]
            if _looks_like_building_name(candidate):
                return FieldExtraction(
                    value=candidate,
                    evidence=f"'{candidate}' — linha anterior a '{lines[i][:40]}'",
                    rule="carimbo_line_before_company",
                    confidence="high",
                )
    labeled = _extract_labeled_value(
        raw_text,
        labels=[r"nome da obra", r"edif[íi]cio", r"empreendimento", r"obra"],
    )
    if labeled:
        value, evidence = labeled
        return FieldExtraction(value=value, evidence=evidence, rule="labeled_value", confidence="medium")
    return None


def _extract_localizacao(raw_text: str) -> FieldExtraction | None:
    result = _find_company_line(raw_text)
    if result:
        i, lines = result
        if i + 1 < len(lines):
            candidate = lines[i + 1]
            if _ADDRESS_PATTERN.search(candidate):
                return FieldExtraction(
                    value=candidate,
                    evidence=f"'{candidate}' — linha após '{lines[i][:40]}'",
                    rule="carimbo_line_after_company",
                    confidence="high",
                )
    labeled = _extract_labeled_value(
        raw_text,
        labels=[r"localiza[çc][ãa]o", r"endere[çc]o", r"local da obra", "local"],
    )
    if labeled:
        value, evidence = labeled
        return FieldExtraction(value=value, evidence=evidence, rule="labeled_value", confidence="medium")
    return None


def _extract_numero_cadastro(raw_text: str) -> FieldExtraction | None:
    labeled = _extract_labeled_value(
        raw_text,
        labels=[
            r"projeto\s*n[°º\.]",
            r"n[°º\.]\s*do\s*projeto",
            r"n[°º\.]\s*(?:do\s*)?processo",
            r"n[°º\.]\s*cadastro",
            r"numero\s+(?:do\s+)?cadastro",
        ],
    )
    if labeled:
        value, evidence = labeled
        return FieldExtraction(value=value, evidence=evidence, rule="labeled_value", confidence="medium")
    return None


def _extract_qtd_hastes(text: str) -> FieldExtraction | None:
    for pattern in (
        r"(\d+)\s*hastes?\s*(?:de\s*)?aterramento",
        r"aterramento[^0-9]{0,30}(\d+)\s*hastes?",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = max(0, match.start() - 5)
            end = min(len(text), match.end() + 5)
            return FieldExtraction(
                value=int(match.group(1)),
                evidence=text[start:end].strip(),
                rule="hastes_regex",
                confidence="high",
            )
    return None


def _extract_perfilado_tipo(raw_text: str) -> FieldExtraction | None:
    match = re.search(
        r"perfilad[oa]\s+(?:tipo\s+)?([A-Z](?:\s*\d+[xX]\d+(?:\s*mm)?)?)",
        raw_text,
        re.IGNORECASE,
    )
    if match:
        return FieldExtraction(
            value=match.group(1).strip(),
            evidence=match.group(0).strip(),
            rule="perfilado_regex",
            confidence="high",
        )
    return None


def _extract_qtd_apartamentos(text: str) -> FieldExtraction | None:
    for pattern in (
        r"(\d+)\s*aptos?\b",
        r"(\d+)\s*apartamentos?\b",
        r"(\d+)\s*unidades?\s*(?:residenciais?|habitacionais?|privativas?)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = max(0, match.start() - 5)
            end = min(len(text), match.end() + 5)
            return FieldExtraction(
                value=int(match.group(1)),
                evidence=text[start:end].strip(),
                rule="apartment_count_regex",
                confidence="medium",
            )
    return None


def _extract_nao_inclusos(raw_text: str) -> dict[str, FieldExtraction]:
    """Detecta sistemas especializados por label de quadro.
    Presença de circuito → False (incluído). Ausência → True (não incluso).
    """
    result: dict[str, FieldExtraction] = {}
    for field_name, patterns in _CIRCUIT_LABELS.items():
        evidence_snippet = None
        for pattern in patterns:
            match = re.search(pattern, raw_text, re.IGNORECASE)
            if match:
                evidence_snippet = match.group(0)
                break
        if evidence_snippet:
            result[field_name] = FieldExtraction(
                value=False,
                evidence=f"Circuito encontrado: '{evidence_snippet}'",
                rule="circuit_label_found",
                confidence="medium",
            )
        else:
            result[field_name] = FieldExtraction(
                value=True,
                evidence=None,
                rule="circuit_label_absent",
                confidence="low",
            )
    return result


def _extract_tem_subestacao(text: str) -> FieldExtraction | None:
    lowered = text.lower()
    negative_patterns = (
        "sem subestacao",
        "sem subestação",
        "nao possui subestacao",
        "não possui subestação",
        "dispensa de subestacao",
        "dispensa de subestação",
    )
    for pattern in negative_patterns:
        idx = lowered.find(pattern)
        if idx != -1:
            evidence = text[max(0, idx - 10):idx + len(pattern) + 10].strip()
            return FieldExtraction(value=False, evidence=evidence, rule="negative_substation_keyword", confidence="high")

    positive_patterns = (
        "subestacao",
        "subestação",
        "cabine primaria",
        "cabine primária",
    )
    for pattern in positive_patterns:
        idx = lowered.find(pattern)
        if idx != -1:
            evidence = text[max(0, idx - 10):idx + len(pattern) + 30].strip()
            return FieldExtraction(value=True, evidence=evidence, rule="positive_substation_keyword", confidence="medium")
    return None


def _extract_tipo_subestacao(raw_text: str, tem_subestacao: bool | None) -> FieldExtraction | None:
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
            cleaned = line.strip(" .;-")
            if cleaned:
                return FieldExtraction(value=cleaned, evidence=cleaned, rule="substation_type_keyword", confidence="medium")

    match = re.search(r"(subesta[çc][ãa]o[^.:\n]{0,80})", raw_text, flags=re.IGNORECASE)
    if match:
        snippet = match.group(1).strip(" .;-")
        return FieldExtraction(value=snippet, evidence=snippet, rule="substation_context_regex", confidence="low")
    return None


def _extract_aterramento_tipo_sistema(text: str) -> FieldExtraction | None:
    for system in ATERRAMENTO_SYSTEMS:
        match = re.search(rf"\b{re.escape(system)}\b", text, flags=re.IGNORECASE)
        if match:
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            return FieldExtraction(
                value=system,
                evidence=text[start:end].strip(),
                rule="aterramento_system_keyword",
                confidence="high",
            )
    return None


def _extract_mt_tensao_kv(text: str) -> FieldExtraction | None:
    result = _extract_numeric_value(
        patterns=[
            r"m[ée]dia\s*tens[ãa]o[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*kV\b",
            r"tens[ãa]o\s+(?:de\s+)?m[ée]dia[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*kV\b",
            r"ramal[^0-9]{0,30}(\d+(?:[.,]\d+)?)\s*kV\b",
        ],
        text=text,
    )
    if result is None:
        return None
    value, evidence = result
    return FieldExtraction(value=value, evidence=evidence, rule="mt_tensao_kv_regex", confidence="high")


def _extract_mt_secao_cabo_mm2(text: str) -> FieldExtraction | None:
    result = _extract_numeric_value(
        patterns=[
            r"se[cç][aã]o(?:\s+do)?\s+cabo[^0-9]{0,20}(\d+(?:[.,]\d+)?)\s*mm[²2]",
            r"ramal[^0-9]{0,30}(\d+(?:[.,]\d+)?)\s*mm[²2]",
        ],
        text=text,
    )
    if result is None:
        return None
    value, evidence = result
    return FieldExtraction(value=value, evidence=evidence, rule="mt_secao_cabo_regex", confidence="high")


def _extract_secao_cabo_cobre_mm2(text: str) -> FieldExtraction | None:
    result = _extract_numeric_value(
        patterns=[
            r"cabo\s+de\s+cobre[^0-9]{0,30}(\d+(?:[.,]\d+)?)\s*mm[²2]",
            r"condutor\s+de\s+(?:prote[çc][ãa]o|aterramento)[^0-9]{0,30}(\d+(?:[.,]\d+)?)\s*mm[²2]",
            r"malha\s+de\s+aterramento[^0-9]{0,30}(\d+(?:[.,]\d+)?)\s*mm[²2]",
        ],
        text=text,
    )
    if result is None:
        return None
    value, evidence = result
    return FieldExtraction(value=value, evidence=evidence, rule="grounding_cable_section_regex", confidence="medium")


def _extract_gerador_tipo_atendimento(text: str) -> FieldExtraction | None:
    match = _GENERATOR_BOARD_RE.search(text)
    if not match:
        return None
    board_context = match.group(0)
    lowered = board_context.lower()

    if re.search(r"\bapartamento|aptos?\b", lowered):
        return FieldExtraction(value="edificio", evidence=board_context.strip(), rule="generator_serves_apartments", confidence="medium")
    if re.search(r"\b(?:[aá]reas?\s+comun[s]?|condomi[n]io)\b", lowered):
        return FieldExtraction(value="condominio", evidence=board_context.strip(), rule="generator_serves_common_areas", confidence="medium")
    if re.search(r"\bparcial\b", lowered):
        return FieldExtraction(value="parcial", evidence=board_context.strip(), rule="generator_partial_keyword", confidence="medium")
    return None


# ── Coverage e mapeamento principal ──────────────────────────────────────────

def _get_nested_value(context: dict[str, Any], path: str) -> Any:
    value: Any = context
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def assess_extraction_coverage(mapping: MappingResult) -> ExtractionReport:
    filled = []
    missing = []
    for field_path in EXTRACTABLE_BY_MAPPER:
        value = _get_nested_value(mapping.context, field_path)
        if value is not None:
            filled.append(field_path)
        else:
            missing.append(field_path)
    return ExtractionReport(
        filled=filled,
        missing=missing,
        pending=list(PENDING_EXTRACTION),
        evidence=mapping.evidence,
    )


def map_extraction_to_partial_context(extraction_result: ProjectExtractionResult) -> MappingResult:
    raw_text = extraction_result.raw_text
    text = _normalize_text(raw_text)

    context: dict[str, Any] = {}
    evidence: dict[str, FieldExtraction] = {}

    def add(path: str, extraction: FieldExtraction | None) -> None:
        _add_field(context, evidence, path, extraction)

    add("obra.construtora", _extract_construtora(raw_text))
    add("obra.nome", _extract_nome_obra(raw_text))
    add("obra.localizacao", _extract_localizacao(raw_text))
    add("obra.numero_cadastro", _extract_numero_cadastro(raw_text))
    add("obra.qtd_apartamentos", _extract_qtd_apartamentos(text))

    tem_sub = _extract_tem_subestacao(text)
    add("energia.tem_subestacao", tem_sub)
    add("energia.tipo_subestacao", _extract_tipo_subestacao(raw_text, tem_sub.value if tem_sub else None))

    add("aterramento.tipo_sistema", _extract_aterramento_tipo_sistema(text))
    add("aterramento.qtd_hastes", _extract_qtd_hastes(text))
    add("aterramento.secao_cabo_cobre_mm2", _extract_secao_cabo_cobre_mm2(text))

    add("mt.tensao_kv", _extract_mt_tensao_kv(text))
    add("mt.secao_cabo_mm2", _extract_mt_secao_cabo_mm2(text))

    add("instalacao.perfilado_tipo", _extract_perfilado_tipo(raw_text))
    add("gerador.tipo_atendimento", _extract_gerador_tipo_atendimento(text))

    for field_name, extraction in _extract_nao_inclusos(raw_text).items():
        add(f"nao_inclusos.{field_name}", extraction)

    return MappingResult(context=context, evidence=evidence)
