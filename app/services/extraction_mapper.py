from __future__ import annotations

import re
import unicodedata
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

TELECOM_EXTRACTABLE_BY_MAPPER = (
    "obra.construtora",
    "obra.nome",
    "obra.localizacao",
    "obra.numero_cadastro",
    "obra.qtd_apartamentos",
)

TELECOM_PENDING_EXTRACTION = (
    "obra.tipo_edificacao",
    "obra.tipologia",
    "obra.qtd_lojas",
    "obra.qtd_restaurantes",
)

GAS_NATURAL_EXTRACTABLE_BY_MAPPER = (
    "obra.construtora",
    "obra.nome",
    "obra.localizacao",
    "obra.numero_cadastro",
    "obra.qtd_apartamentos",
)

GAS_NATURAL_PENDING_EXTRACTION = (
    "obra.tipo_edificacao",
    "obra.tipologia",
    "obra.qtd_lojas",
    "obra.qtd_restaurantes",
    "crm.pavimento",
    "dimensionamento.qtd_fogao",
    "dimensionamento.qtd_aquecedor",
    "dimensionamento.qtd_churrasqueira",
    "soma.qtd_pontos_de_utilizacao",
    "ramal.primario_diametro",
    "ramal.primario_material",
    "ramal.primario_pavimento",
    "valvula.esfera_diametro",
    "numero.prancha",
    "teto_ou_piso",
)

GLP_EXTRACTABLE_BY_MAPPER = (
    "obra.construtora",
    "obra.nome",
    "obra.localizacao",
    "obra.numero_cadastro",
    "obra.qtd_apartamentos",
)

GLP_PENDING_EXTRACTION = (
    "obra.tipo_edificacao",
    "obra.tipologia",
    "obra.qtd_lojas",
    "obra.qtd_restaurantes",
    "abastecimento.qtd_tanques",
    "abastecimento.pavimento",
    "dimensionamento.qtd_fogao",
    "dimensionamento.qtd_aquecedor",
    "dimensionamento.qtd_churrasqueira",
    "soma.qtd_pontos_de_utilizacao",
    "ramal.primario_diametro",
    "ramal.primario_material",
    "ramal.primario_pavimento",
    "numero.prancha",
    "teto_ou_piso",
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
    cross_validation: dict[str, Any] | None = None


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
_PROJECT_NUMBER_PATTERN = re.compile(r"\b\d{2,6}/\d{4}\b")

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


def _ascii_key(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.casefold()).strip()


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
    best_index: int | None = None
    best_score = -10**9
    negative_markers = (
        "expressamente proibido",
        "prévia autorização",
        "previa autorizacao",
        "reprodução total",
        "reproducao total",
        "veiculação a terceiros",
        "veiculacao a terceiros",
        "projetado por",
        "quadro de controle",
    )
    for i, line in enumerate(lines):
        lowered = line.lower()
        if not _COMPANY_PATTERN.search(line) or len(line) <= 10:
            continue
        score = 0
        if "ltda" in lowered:
            score += 10
        if "engenharia" in lowered or "incorpora" in lowered or "constru" in lowered:
            score += 5
        if any(marker in lowered for marker in negative_markers):
            score -= 20
        if len(line) > 90:
            score -= 8
        if i > 0 and _looks_like_building_name(lines[i - 1]):
            score += 5
        if i + 1 < len(lines) and _ADDRESS_PATTERN.search(lines[i + 1]):
            score += 8
        if score > best_score:
            best_score = score
            best_index = i
    if best_index is not None:
        return best_index, lines
    return None


def _extract_labeled_value(raw_text: str, labels: list[str]) -> tuple[str, str] | None:
    """Retorna (valor, linha_evidência) ou None."""
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    def _looks_like_another_label(value: str) -> bool:
        stripped = value.strip()
        if not stripped:
            return True
        if stripped.endswith(":"):
            return True
        if re.fullmatch(r"[A-Za-zÀ-ÿ ]{1,20}:", stripped):
            return True
        if stripped.lower() in {
            "escala", "projeto", "edifício", "edificio", "local",
            "construtor", "data", "desenho", "proprietário", "proprietario",
        }:
            return True
        return False
    for i, line in enumerate(lines):
        for label in labels:
            pattern = re.compile(rf"^{label}\s*[:\-]\s*(.+)$", re.IGNORECASE)
            match = pattern.search(line)
            if match:
                value = match.group(1).strip(" .;-")
                if value and not _looks_like_another_label(value):
                    return value, line
            label_only = re.compile(rf"^{label}\s*[:\-]?\s*$", re.IGNORECASE)
            if label_only.match(line) and i + 1 < len(lines):
                value = lines[i + 1].strip(" .;-")
                if value and not _looks_like_another_label(value):
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
        company_line = lines[i]
        # Strip label prefix if the line is "CONSTRUTORA: VALUE" style
        labeled = _extract_labeled_value(
            company_line,
            labels=[r"construtora", r"empresa construtora", r"construtor", r"propriet[áa]rio"],
        )
        value = labeled[0] if labeled else company_line
        return FieldExtraction(value=value, evidence=company_line, rule="carimbo_company_pattern", confidence="high")
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
    regex_match = _PROJECT_NUMBER_PATTERN.search(raw_text)
    if regex_match:
        value = regex_match.group(0)
        return FieldExtraction(
            value=value,
            evidence=value,
            rule="project_number_regex",
            confidence="high",
        )

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
    apartment_ids = {
        int(match)
        for match in re.findall(r"\bAP(?:TO|\.)\s*0?(\d{2,3})\b", text, re.IGNORECASE)
    }
    if len(apartment_ids) >= 4:
        return FieldExtraction(
            value=len(apartment_ids),
            evidence=f"{len(apartment_ids)} unidades únicas identificadas por AP/APTO",
            rule="unique_apartment_ids",
            confidence="high",
        )

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


def _extract_telecom_tipo_edificacao(text: str) -> FieldExtraction | None:
    lowered = text.lower()
    if "apartamentos" in lowered or "apto" in lowered or "suíte" in lowered or "suite" in lowered:
        return FieldExtraction(
            value="Residencial Multifamiliar",
            evidence="presença de apartamentos/suítes no projeto",
            rule="telecom_residential_inference",
            confidence="medium",
        )
    if "loja" in lowered or "restaurante" in lowered or "mini - market" in lowered or "mini-market" in lowered:
        return FieldExtraction(
            value="Misto",
            evidence="presença de ocupação comercial no projeto",
            rule="telecom_mixed_use_inference",
            confidence="low",
        )
    return None


def _extract_telecom_tipologia(text: str) -> FieldExtraction | None:
    apartment_floors = {
        int(match[0])
        for match in re.findall(r"\bAP(?:TO|\.)\s*0?(\d)(\d{2})\b", text, re.IGNORECASE)
    }
    has_subsolo = "subsolo" in text.lower()
    has_terreo = "térreo" in text.lower() or "terreo" in text.lower()
    has_coberta = "coberta" in text.lower() or "cobertura" in text.lower()

    if apartment_floors:
        parts = []
        if has_subsolo:
            parts.append("Subsolo")
        if has_terreo:
            parts.append("térreo")
        parts.append(f"{max(apartment_floors)} pavimentos")
        if has_coberta:
            parts.append("cobertura")
        value = ", ".join(parts)
        return FieldExtraction(
            value=value,
            evidence=f"andares identificados por apartamentos: {sorted(apartment_floors)}",
            rule="telecom_floor_typology_inference",
            confidence="medium",
        )
    return None


def _extract_gas_natural_tipologia(
    text: str,
    extraction_result: ProjectExtractionResult,
) -> FieldExtraction | None:
    text_result = _extract_telecom_tipologia(text)
    if text_result is not None:
        return text_result

    filename_text = " ".join(
        f"{source_file.original_filename} {source_file.stored_filename}"
        for source_file in extraction_result.source_files
    )
    normalized = _ascii_key(filename_text)
    floors = [
        int(match.group(1))
        for match in re.finditer(r"\b(\d+)\s*(?:e\s*)?pav(?:imento|imentos)?\b", normalized)
    ]
    if not floors:
        return None

    parts = []
    if "subsolo" in normalized:
        parts.append("Subsolo")
    if "terreo" in normalized:
        parts.append("térreo")

    max_floor = max(floors)
    floor_label = "pavimento" if max_floor == 1 else "pavimentos"
    parts.append(f"{max_floor} {floor_label}")

    if "cobertura" in normalized or "coberta" in normalized:
        parts.append("cobertura")

    return FieldExtraction(
        value=", ".join(parts),
        evidence=", ".join(source_file.original_filename for source_file in extraction_result.source_files),
        rule="gas_natural_sheet_filename_typology_inference",
        confidence="low",
    )


def _extract_telecom_qtd_lojas(text: str) -> FieldExtraction | None:
    lowered = text.lower()
    match = re.search(r"(\d+)\s*lojas?\b", lowered, re.IGNORECASE)
    if match:
        return FieldExtraction(
            value=int(match.group(1)),
            evidence=match.group(0),
            rule="telecom_store_count_regex",
            confidence="medium",
        )
    if "mini - market" in lowered or "mini-market" in lowered:
        return FieldExtraction(
            value=0,
            evidence="projeto residencial com mini-market de apoio e sem lojas identificadas",
            rule="telecom_no_stores_residential_default",
            confidence="low",
        )
    if "apartamentos" in lowered or "apto" in lowered:
        return FieldExtraction(
            value=0,
            evidence="projeto residencial sem lojas explicitadas",
            rule="telecom_no_stores_residential_default",
            confidence="low",
        )
    return None


def _extract_telecom_qtd_restaurantes(text: str) -> FieldExtraction | None:
    lowered = text.lower()
    match = re.search(r"(\d+)\s*restaurantes?\b", lowered, re.IGNORECASE)
    if match:
        return FieldExtraction(
            value=int(match.group(1)),
            evidence=match.group(0),
            rule="telecom_restaurant_count_regex",
            confidence="medium",
        )
    if "gourmet" in lowered and "restaurante" not in lowered:
        return FieldExtraction(
            value=0,
            evidence="áreas gourmet sem restaurante identificado",
            rule="telecom_no_restaurants_default",
            confidence="low",
        )
    if "apartamentos" in lowered or "apto" in lowered:
        return FieldExtraction(
            value=0,
            evidence="projeto residencial sem restaurantes explicitados",
            rule="telecom_no_restaurants_default",
            confidence="low",
        )
    return None


def _extract_glp_quantity_from_patterns(
    text: str,
    patterns: tuple[str, ...],
    rule: str,
) -> FieldExtraction | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return FieldExtraction(
                value=int(match.group(1)),
                evidence=match.group(0),
                rule=rule,
                confidence="medium",
            )
    return None


def _extract_glp_qtd_fogao(text: str) -> FieldExtraction | None:
    return _extract_glp_quantity_from_patterns(
        text=text,
        patterns=(
            r"(\d+)\s*fog(?:[ãa]o|[õo]es?)\b",
            r"fog(?:[ãa]o|[õo]es?)\s*[:\-]?\s*(\d+)\b",
        ),
        rule="glp_fogao_count_regex",
    )


def _extract_glp_qtd_aquecedor(text: str) -> FieldExtraction | None:
    extraction = _extract_glp_quantity_from_patterns(
        text=text,
        patterns=(
            r"(\d+)\s*aquecedores?\b",
            r"aquecedores?\s*[:\-]?\s*(\d+)\b",
        ),
        rule="glp_heater_count_regex",
    )
    if extraction is not None:
        return extraction

    if "aquecedor" not in text.lower() and "aquecedores" not in text.lower():
        return FieldExtraction(
            value=0,
            evidence="nenhuma ocorrência de aquecedor no texto extraído do projeto",
            rule="glp_no_heater_default",
            confidence="low",
        )
    return None


def _extract_glp_qtd_churrasqueira(text: str) -> FieldExtraction | None:
    return _extract_glp_quantity_from_patterns(
        text=text,
        patterns=(
            r"(\d+)\s*churrasqueiras?\b",
            r"churrasqueiras?\s*[:\-]?\s*(\d+)\b",
        ),
        rule="glp_churrasqueira_count_regex",
    )


def _extract_glp_total_points_from_quantitative_tables(text: str) -> FieldExtraction | None:
    matches = re.findall(
        r"\(\s*\d+\s*PAV[^)]*?=\s*(\d+)\s*PONTOS\s*\)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not matches:
        return None

    totals = [int(value) for value in matches]
    return FieldExtraction(
        value=sum(totals),
        evidence=" + ".join(matches),
        rule="glp_quantitative_table_points_sum",
        confidence="high",
    )


def _normalize_gas_natural_pavimento(value: str) -> str:
    key = _ascii_key(value)
    if "terreo" in key:
        return "térreo"
    if "subsolo" in key:
        return "subsolo"
    if "cobertura" in key or "coberta" in key:
        return "cobertura"
    pavimento_match = re.search(r"\b(\d+)\s*(?:o|pav|pavimento)\b", key)
    if pavimento_match:
        return f"{int(pavimento_match.group(1))} pavimento"
    return value.strip().lower()


def _extract_gas_natural_floor_near_label(
    text: str,
    label_pattern: str,
    rule: str,
) -> FieldExtraction | None:
    floor_pattern = r"(subsolo|t[ée]rreo|terreo|cobertura|coberta|\d+[ºo]?\s*pav(?:imento)?)"
    patterns = (
        rf"\b{label_pattern}\b.{{0,120}}\b{floor_pattern}\b",
        rf"\b{floor_pattern}\b.{{0,120}}\b{label_pattern}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            floor = match.group(1)
            return FieldExtraction(
                value=_normalize_gas_natural_pavimento(floor),
                evidence=_normalize_text(match.group(0)),
                rule=rule,
                confidence="medium",
            )
    return None


def _extract_gas_natural_crm_pavimento(text: str) -> FieldExtraction | None:
    return _extract_gas_natural_floor_near_label(
        text=text,
        label_pattern=r"CRM",
        rule="gas_natural_crm_floor_regex",
    )


def _extract_gas_natural_ramal_pavimento(text: str) -> FieldExtraction | None:
    return _extract_gas_natural_floor_near_label(
        text=text,
        label_pattern=r"ramal(?:\s+interno)?(?:\s+prim[aá]rio)?",
        rule="gas_natural_primary_branch_floor_regex",
    )


def _extract_gas_natural_ramal_diametro(text: str) -> FieldExtraction | None:
    diameter_value = (
        r"((?:\d+\s+)?\d+\s*/\s*\d+\s*(?:\"|pol(?:egadas?)?)|"
        r"\d+(?:[,.]\d+)?\s*mm|"
        r"\d+(?:[,.]\d+)?\s*(?:\"|pol(?:egadas?)?))"
    )
    patterns = (
        rf"ramal(?:\s+interno)?(?:\s+prim[aá]rio)?.{{0,120}}?(?:DN|Ø|diam(?:etro)?|di[âa]metro)?\s*{diameter_value}",
        rf"(?:DN|Ø|diam(?:etro)?|di[âa]metro)?\s*{diameter_value}.{{0,120}}?ramal(?:\s+interno)?(?:\s+prim[aá]rio)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return FieldExtraction(
                value=_normalize_text(match.group(1)),
                evidence=_normalize_text(match.group(0)),
                rule="gas_natural_primary_branch_diameter_regex",
                confidence="medium",
            )
    return None


def _extract_gas_natural_ramal_material(text: str) -> FieldExtraction | None:
    match = re.search(
        r"ramal(?:\s+interno)?(?:\s+prim[aá]rio)?.{0,160}",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    window = match.group(0) if match else text
    key = _ascii_key(window)
    materials = (
        ("aco carbono", "aço carbono"),
        ("aco galvanizado", "aço galvanizado"),
        ("cobre", "cobre"),
        ("pead", "PEAD"),
    )
    for marker, value in materials:
        if marker in key:
            return FieldExtraction(
                value=value,
                evidence=_normalize_text(window),
                rule="gas_natural_primary_branch_material_regex",
                confidence="medium",
            )
    return None


def _extract_gas_natural_valvula_esfera_diametro(text: str) -> FieldExtraction | None:
    pattern = r"v[áa]lvula(?:\s+de)?\s+esfera.{0,80}?(?:DN|Ø)?\s*(\d+(?:[,.]\d+)?)\s*mm"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    value = f"{match.group(1).replace(',', '.')} mm"
    return FieldExtraction(
        value=value,
        evidence=_normalize_text(match.group(0)),
        rule="gas_natural_ball_valve_diameter_regex",
        confidence="medium",
    )


def _extract_gas_natural_teto_ou_piso(text: str) -> FieldExtraction | None:
    patterns = (
        r"ramal(?:\s+interno)?(?:\s+prim[aá]rio)?.{0,120}\b(teto|piso|contrapiso|enterrado)\b",
        r"\bpelo\s+(teto|piso|contrapiso)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            value = _ascii_key(match.group(1))
            return FieldExtraction(
                value=value,
                evidence=_normalize_text(match.group(0)),
                rule="gas_natural_branch_path_regex",
                confidence="medium",
            )
    return None


def _extract_gas_natural_qtd_churrasqueira(text: str) -> FieldExtraction | None:
    for pattern in (
        r"churrasqueiras?\s*[:\-]?\s*(\d+)\b",
        r"\b(\d+)[ \t]*churrasqueiras?\b",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return FieldExtraction(
                value=int(match.group(1)),
                evidence=match.group(0),
                rule="gas_natural_churrasqueira_count_regex",
                confidence="medium",
            )

    key = _ascii_key(text)
    if "churrasqueira" not in key and ("fogao" in key or "pontos" in key):
        return FieldExtraction(
            value=0,
            evidence="dimensionamento sem churrasqueira identificada",
            rule="gas_natural_no_churrasqueira_default",
            confidence="low",
        )
    return None


def _extract_gas_natural_qtd_aquecedor(text: str) -> FieldExtraction | None:
    extraction = _extract_glp_quantity_from_patterns(
        text=text,
        patterns=(
            r"(\d+)[ \t]*aquecedores?\b",
            r"aquecedores?\s*[:\-]?\s*(\d+)\b",
        ),
        rule="gas_natural_heater_count_regex",
    )
    if extraction is not None:
        return extraction

    key = _ascii_key(text)
    if "aquecedor" not in key and ("fogao" in key or "pontos" in key):
        return FieldExtraction(
            value=0,
            evidence="dimensionamento sem aquecedor identificado",
            rule="gas_natural_no_heater_default",
            confidence="low",
        )
    return None


def _extract_gas_natural_numero_prancha(
    extraction_result: ProjectExtractionResult,
) -> FieldExtraction | None:
    source_files = extraction_result.source_files
    if not source_files:
        return None

    total_files = extraction_result.signals.get("total_files")
    if not isinstance(total_files, int) or total_files <= 0:
        total_files = len(source_files)

    candidates = sorted(
        source_files,
        key=lambda sf: 0 if "corte" in _ascii_key(sf.original_filename) else 1,
    )
    for source_file in candidates:
        match = re.match(r"\D*(\d{1,2})", source_file.original_filename)
        if match:
            sheet_number = int(match.group(1))
            return FieldExtraction(
                value=f"{sheet_number:02d}/{total_files:02d}",
                evidence=source_file.original_filename,
                rule="gas_natural_sheet_number_from_filename",
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

    pending = []
    for field_path in PENDING_EXTRACTION:
        value = _get_nested_value(mapping.context, field_path)
        if value is not None:
            filled.append(field_path)
        else:
            pending.append(field_path)

    return ExtractionReport(
        filled=filled,
        missing=missing,
        pending=pending,
        evidence=mapping.evidence,
    )


def assess_telecom_extraction_coverage(mapping: MappingResult) -> ExtractionReport:
    filled = []
    missing = []
    for field_path in TELECOM_EXTRACTABLE_BY_MAPPER:
        value = _get_nested_value(mapping.context, field_path)
        if value is not None:
            filled.append(field_path)
        else:
            missing.append(field_path)

    pending = []
    for field_path in TELECOM_PENDING_EXTRACTION:
        value = _get_nested_value(mapping.context, field_path)
        if value is not None:
            filled.append(field_path)
        else:
            pending.append(field_path)

    return ExtractionReport(
        filled=filled,
        missing=missing,
        pending=pending,
        evidence=mapping.evidence,
    )


def assess_gas_natural_extraction_coverage(mapping: MappingResult) -> ExtractionReport:
    filled = []
    missing = []
    for field_path in GAS_NATURAL_EXTRACTABLE_BY_MAPPER:
        value = _get_nested_value(mapping.context, field_path)
        if value is not None:
            filled.append(field_path)
        else:
            missing.append(field_path)

    pending = []
    for field_path in GAS_NATURAL_PENDING_EXTRACTION:
        value = _get_nested_value(mapping.context, field_path)
        if value is not None:
            filled.append(field_path)
        else:
            pending.append(field_path)

    return ExtractionReport(
        filled=filled,
        missing=missing,
        pending=pending,
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


def map_extraction_to_partial_telecom_context(
    extraction_result: ProjectExtractionResult,
) -> MappingResult:
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
    add("obra.tipo_edificacao", _extract_telecom_tipo_edificacao(text))
    add("obra.tipologia", _extract_telecom_tipologia(text))
    add("obra.qtd_lojas", _extract_telecom_qtd_lojas(text))
    add("obra.qtd_restaurantes", _extract_telecom_qtd_restaurantes(text))

    return MappingResult(context=context, evidence=evidence)


def map_extraction_to_partial_gas_natural_context(
    extraction_result: ProjectExtractionResult,
) -> MappingResult:
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
    add("obra.tipo_edificacao", _extract_telecom_tipo_edificacao(text))
    add("obra.tipologia", _extract_gas_natural_tipologia(text, extraction_result))
    add("obra.qtd_lojas", _extract_telecom_qtd_lojas(text))
    add("obra.qtd_restaurantes", _extract_telecom_qtd_restaurantes(text))
    add("crm.pavimento", _extract_gas_natural_crm_pavimento(raw_text))
    add("dimensionamento.qtd_fogao", _extract_glp_qtd_fogao(text))
    add("dimensionamento.qtd_aquecedor", _extract_gas_natural_qtd_aquecedor(text))
    add("dimensionamento.qtd_churrasqueira", _extract_gas_natural_qtd_churrasqueira(text))
    add("soma.qtd_pontos_de_utilizacao", _extract_glp_total_points_from_quantitative_tables(raw_text))
    add("ramal.primario_diametro", _extract_gas_natural_ramal_diametro(raw_text))
    add("ramal.primario_material", _extract_gas_natural_ramal_material(raw_text))
    add("ramal.primario_pavimento", _extract_gas_natural_ramal_pavimento(raw_text))
    add("valvula.esfera_diametro", _extract_gas_natural_valvula_esfera_diametro(raw_text))
    add("numero.prancha", _extract_gas_natural_numero_prancha(extraction_result))
    add("teto_ou_piso", _extract_gas_natural_teto_ou_piso(raw_text))

    return MappingResult(context=context, evidence=evidence)


def assess_glp_extraction_coverage(mapping: MappingResult) -> ExtractionReport:
    filled = []
    missing = []
    for field_path in GLP_EXTRACTABLE_BY_MAPPER:
        value = _get_nested_value(mapping.context, field_path)
        if value is not None:
            filled.append(field_path)
        else:
            missing.append(field_path)

    pending = []
    for field_path in GLP_PENDING_EXTRACTION:
        value = _get_nested_value(mapping.context, field_path)
        if value is not None:
            filled.append(field_path)
        else:
            pending.append(field_path)

    return ExtractionReport(
        filled=filled,
        missing=missing,
        pending=pending,
        evidence=mapping.evidence,
    )


def map_extraction_to_partial_glp_context(
    extraction_result: ProjectExtractionResult,
) -> MappingResult:
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
    add("obra.tipo_edificacao", _extract_telecom_tipo_edificacao(text))
    add("obra.tipologia", _extract_telecom_tipologia(text))
    add("obra.qtd_lojas", _extract_telecom_qtd_lojas(text))
    add("obra.qtd_restaurantes", _extract_telecom_qtd_restaurantes(text))
    add("dimensionamento.qtd_fogao", _extract_glp_qtd_fogao(text))
    add("dimensionamento.qtd_aquecedor", _extract_glp_qtd_aquecedor(text))
    add("dimensionamento.qtd_churrasqueira", _extract_glp_qtd_churrasqueira(text))
    add("soma.qtd_pontos_de_utilizacao", _extract_glp_total_points_from_quantitative_tables(raw_text))

    return MappingResult(context=context, evidence=evidence)
