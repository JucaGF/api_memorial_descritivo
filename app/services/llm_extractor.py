from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.services.project_extractor import ExtractedSourceFile

logger = logging.getLogger(__name__)
RICH_TEXT_ONLY_THRESHOLD = 4000
GLP_TEXT_ONLY_THRESHOLD = RICH_TEXT_ONLY_THRESHOLD


@dataclass(frozen=True)
class LLMExtractionRunResult:
    context: dict[str, Any]
    cross_validation: dict[str, Any] | None = None


@dataclass(frozen=True)
class BatchFileExtractionResult:
    filename: str
    extraction_type: str
    payload: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class BatchExtractionResult:
    batch_index: int
    files: list[str]
    per_file_results: list[BatchFileExtractionResult]
    merged_payload: dict[str, Any]


@dataclass(frozen=True)
class ExtractionStrategy:
    name: str
    cross_validation_intro: str
    text_format: type[BaseModel]
    single_file_extractor: Any
    batch_merger: Any


# ── Extraction schema ─────────────────────────────────────────────────────────


class ObraExtraction(BaseModel):
    construtora: str | None = None
    nome: str | None = None
    localizacao: str | None = None
    numero_cadastro: str | None = None
    tipo_edificacao: str | None = None
    tipologia: str | None = None
    qtd_apartamentos: int | None = None
    qtd_lojas: int | None = None
    qtd_restaurantes: int | None = None


class EnergiaExtraction(BaseModel):
    tem_subestacao: bool | None = None
    tipo_subestacao: str | None = None
    potencia_transformador_kva: float | None = None
    tap_descricao: str | None = None
    tensao_secundaria: str | None = None


class AterramentoExtraction(BaseModel):
    tipo_sistema: str | None = None
    qtd_hastes: int | None = None
    secao_cabo_cobre_mm2: float | None = None
    secao_cabo_malha_mm2: float | None = None
    local_bep: str | None = None


class MTExtraction(BaseModel):
    tensao_kv: float | None = None
    diametro_eletroduto_pol: float | None = None
    tipo_cabo: str | None = None
    temperatura_cabo: float | None = None
    classe_isolacao: str | None = None
    secao_cabo_mm2: float | None = None


class GeradorExtraction(BaseModel):
    tipo_atendimento: str | None = None
    qtd: int | None = None
    potencia_kva: float | None = None
    circuitos_atendidos: str | None = None


class NaoInclusosExtraction(BaseModel):
    cpct: bool | None = None
    cftv: bool | None = None
    alarme_patrimonial: bool | None = None
    sonorizacao: bool | None = None
    alarme_incendio: bool | None = None
    automacao: bool | None = None


class InstalacaoExtraction(BaseModel):
    perfilado_tipo: str | None = None


class LLMExtraction(BaseModel):
    obra: ObraExtraction = ObraExtraction()
    energia: EnergiaExtraction = EnergiaExtraction()
    aterramento: AterramentoExtraction = AterramentoExtraction()
    mt: MTExtraction = MTExtraction()
    gerador: GeradorExtraction = GeradorExtraction()
    nao_inclusos: NaoInclusosExtraction = NaoInclusosExtraction()
    instalacao: InstalacaoExtraction = InstalacaoExtraction()
    observacoes: str | None = None


class TelecomLLMExtraction(BaseModel):
    obra: ObraExtraction = ObraExtraction()
    observacoes: str | None = None


class CRMExtraction(BaseModel):
    pavimento: str | None = None


class DimensionamentoExtraction(BaseModel):
    qtd_fogao: int | None = None
    qtd_aquecedor: int | None = None
    qtd_churrasqueira: int | None = None


class SomaExtraction(BaseModel):
    qtd_pontos_de_utilizacao: int | None = None


class RamalExtraction(BaseModel):
    primario_diametro: str | None = None
    primario_material: str | None = None
    primario_pavimento: str | None = None


class ValvulaExtraction(BaseModel):
    esfera_diametro: str | None = None


class NumeroExtraction(BaseModel):
    prancha: str | None = None


class GasNaturalLLMExtraction(BaseModel):
    obra: ObraExtraction = ObraExtraction()
    crm: CRMExtraction = CRMExtraction()
    dimensionamento: DimensionamentoExtraction = DimensionamentoExtraction()
    soma: SomaExtraction = SomaExtraction()
    ramal: RamalExtraction = RamalExtraction()
    valvula: ValvulaExtraction = ValvulaExtraction()
    numero: NumeroExtraction = NumeroExtraction()
    teto_ou_piso: str | None = None
    observacoes: str | None = None


class AbastecimentoExtraction(BaseModel):
    # qtd_tanques representa a QUANTIDADE DE ABRIGOS de gás GLP do
    # empreendimento — NÃO a quantidade de recipientes/cilindros P-190 que
    # ficam dentro do abrigo. Um abrigo típico contém múltiplos P-190 e ainda
    # assim qtd_tanques deve ser 1. O nome do campo é histórico; a semântica
    # correta é "número de abrigos".
    qtd_tanques: int | None = None
    pavimento: str | None = None


class GlpLLMExtraction(BaseModel):
    obra: ObraExtraction = ObraExtraction()
    abastecimento: AbastecimentoExtraction = AbastecimentoExtraction()
    dimensionamento: DimensionamentoExtraction = DimensionamentoExtraction()
    soma: SomaExtraction = SomaExtraction()
    ramal: RamalExtraction = RamalExtraction()
    numero: NumeroExtraction = NumeroExtraction()
    teto_ou_piso: str | None = None
    observacoes: str | None = None


class TanquesV2LLMExtraction(BaseModel):
    quantidade: int | None = None
    tipo: str | None = None
    capacidade_kg: float | None = None
    qtd_abrigos: int | None = None


class PontosUtilizacaoV2LLMExtraction(BaseModel):
    fogao: int | None = None
    churrasqueira: int | None = None
    aquecedor: int | None = None
    outros: int | None = None
    total_extraido: int | None = None


class DiametrosV2LLMExtraction(BaseModel):
    tubulacao_principal: str | None = None
    valvula_esfera: str | None = None


class AbastecimentoV2LLMExtraction(BaseModel):
    pavimento: str | None = None


class DimensionamentoV2LLMExtraction(BaseModel):
    qtd_fogao: int | None = None
    qtd_aquecedor: int | None = None
    qtd_churrasqueira: int | None = None
    qtd_outros: int | None = None


class GlpV2LLMExtraction(BaseModel):
    obra: ObraExtraction = ObraExtraction()
    tanques: TanquesV2LLMExtraction = TanquesV2LLMExtraction()
    abastecimento: AbastecimentoV2LLMExtraction = AbastecimentoV2LLMExtraction()
    dimensionamento: DimensionamentoV2LLMExtraction = DimensionamentoV2LLMExtraction()
    pontos_utilizacao: PontosUtilizacaoV2LLMExtraction = PontosUtilizacaoV2LLMExtraction()
    diametros: DiametrosV2LLMExtraction = DiametrosV2LLMExtraction()
    ramal: RamalExtraction = RamalExtraction()
    numero: NumeroExtraction = NumeroExtraction()
    teto_ou_piso: str | None = None
    observacoes: str | None = None


# ── Prompts ───────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = """\
You are an expert structured data extractor for Brazilian electrical engineering projects.

You will receive page images from technical drawings (pranchas) of an electrical project, \
along with supplementary OCR text. The images are the PRIMARY source of truth — use visual \
inspection of diagrams, title blocks, legends, and annotations. Use the OCR text only to \
confirm or complement what you see in the images.

## Where to look for each field

### obra (project info)
Look at the TITLE BLOCK (carimbo) — usually bottom-right corner of each drawing page.
- construtora: company name (look for "LTDA", "S.A.", "ENGENHARIA", "INCORPORAÇÃO")
- nome: building/project name (usually the largest text in the title block, above the company)
- localizacao: address (look for "AV.", "RUA", city, state)
- numero_cadastro: project number (look for "PROJETO N°", "N° DO PROCESSO")
- tipo_edificacao: "residencial", "comercial", or "misto" — infer from the drawings
- tipologia: e.g. "torre única", "2 torres", "condomínio horizontal"
- qtd_apartamentos: count apartment units from unit lists or load tables
- qtd_lojas: count commercial units if present
- qtd_restaurantes: count restaurants if present (0 if none)

### energia (power supply)
Look at the SINGLE-LINE DIAGRAM (diagrama unifilar geral) for the main power distribution.
- tem_subestacao: true if you see a transformer symbol, "subestação", or "cabine primária"
- tipo_subestacao: description (e.g. "subestação abrigada", "subestação aérea simplificada")
- potencia_transformador_kva: transformer rated power in kVA (e.g. 500, 1000, 1500)
- tap_descricao: transformer tap setting (e.g. "tap nominal", "tap +2,5%")
- tensao_secundaria: secondary voltage (e.g. "220/127V", "380/220V")

### mt (medium voltage)
Look at the MT section of the single-line diagram. MT = média tensão, typically 13.8kV or 15kV.
CRITICAL: Do NOT confuse with BT (baixa tensão: 220V/380V). MT voltages are 13.8kV, 15kV, 34.5kV.
- tensao_kv: voltage of the MT supply line (13.8 or 15, NOT 380 or 220)
- diametro_eletroduto_pol: conduit diameter in inches for MT cables
- tipo_cabo: MT cable type (e.g. "XLPE", "EPR")
- temperatura_cabo: cable rated temperature in °C
- classe_isolacao: insulation class (e.g. "8.7/15kV", "12/20kV")
- secao_cabo_mm2: MT cable cross-section in mm² (typically 35, 50, 70, 95, 120, 150, 185, 240)

### aterramento (grounding)
Look at the GROUNDING DETAIL drawing and legend.
- tipo_sistema: MUST be exactly one of: "TN-S", "TN-C", "TN-C-S", "TT", "IT"
- qtd_hastes: count grounding rods from the detail or legend
- secao_cabo_cobre_mm2: copper cable cross-section for grounding conductor in mm²
- secao_cabo_malha_mm2: grounding mesh cable cross-section in mm²
- local_bep: location of the BEP (e.g. "subsolo", "térreo", "casa de máquinas")

### gerador (generator)
Look at the GENERATOR section of the single-line diagram or the generator panel diagram.
- tipo_atendimento: MUST be exactly one of:
  "edificio" (serves the entire building including apartments),
  "condominio" (serves only common areas),
  "parcial" (serves specific circuits like pumps/elevators)
- qtd: number of generator sets
- potencia_kva: generator rated power in kVA
- circuitos_atendidos: when tipo_atendimento="parcial", list which circuits (e.g. "elevadores, bombas de recalque")

### nao_inclusos (systems NOT included in the electrical project)
Examine the single-line diagrams and panel schedules for dedicated circuit boards.
If a dedicated board/circuit EXISTS for a system → that system IS included → set to false.
If NO dedicated board/circuit is found → system is NOT included → set to true.
- cpct: CPCT system (portaria/interfone)
- cftv: CCTV system
- alarme_patrimonial: security alarm
- sonorizacao: sound system
- alarme_incendio: fire alarm
- automacao: building automation

### instalacao (installation details)
Look at construction details and legends for cable tray/perfilado information.
- perfilado_tipo: cable tray type (e.g. "C 38x38mm", "U 50x50mm")

## Rules
- Extract ONLY from evidence visible in the images or OCR text.
- Return null for any field without sufficient evidence.
- NEVER invent or guess values.
- Numeric fields must be numbers, not strings.
- In observacoes, briefly note any ambiguities or extraction limitations.
"""

MERGE_PROMPT = """\
You are merging structured extractions from multiple PDF files of the SAME electrical project.

Each extraction below comes from a different file (drawing sheet) of the project. \
Different sheets contain different information — for example, the general single-line diagram \
has power supply info, grounding details are on the grounding sheet, apartment layouts show \
unit counts, etc.

Your task: produce a SINGLE unified extraction by intelligently merging the per-file results.

Rules:
- When multiple files provide the SAME field with DIFFERENT values, prefer the value from the \
  file most likely to be authoritative (e.g. single-line diagram for energia/MT, grounding detail \
  for aterramento, title block for obra info).
- When only one file provides a field, use that value.
- Return null only when NO file provided a value.
- For nao_inclusos: if ANY file shows a dedicated circuit/board for a system, set it to false \
  (system IS included). Only set to true if NO file shows evidence of it.
- In observacoes, note any conflicts you resolved and which file you preferred.

Per-file extractions:
"""

TELECOM_EXTRACTION_PROMPT = """\
You are an expert structured data extractor for Brazilian telecommunications engineering projects.

You will receive page images from telecom project drawings and memorial-related files, along with \
supplementary OCR text. The images are the PRIMARY source of truth. Use OCR text only to confirm \
or complement what is visible.

Your job is to extract ONLY the fields required by the telecom memorial v1 contract.

## Where to look for each field

### obra (project info)
Look at the TITLE BLOCK (carimbo), cover sheet, legends, unit schedules, or project notes.
- construtora: company name responsible for the project or development
- nome: project/building/enterprise name
- localizacao: address, city/state, or project location
- numero_cadastro: project/process/reference number shown in the title block
- tipo_edificacao: building type such as "residencial", "comercial", or "misto"
- tipologia: enterprise typology such as "torre única", "2 torres", or "condomínio"
- qtd_apartamentos: apartment count from schedules or notes
- qtd_lojas: commercial unit/store count from schedules or notes
- qtd_restaurantes: restaurant count from schedules or notes

## Rules
- Extract ONLY from evidence visible in the images or OCR text.
- Return null for any field without sufficient evidence.
- NEVER invent or guess values.
- Numeric fields must be numbers, not strings.
- In observacoes, briefly note any ambiguities or extraction limitations.
"""

TELECOM_MERGE_PROMPT = """\
You are merging structured extractions from multiple files of the SAME telecom project.

Different files may contribute different project metadata, title-block information, or unit counts.

Your task: produce a SINGLE unified extraction for the telecom memorial context.

Rules:
- When multiple files provide the SAME field with DIFFERENT values, prefer the value from the \
  most authoritative file, such as the project cover, title block, or general notes sheet.
- When only one file provides a field, use that value.
- Return null only when NO file provided a value.
- In observacoes, note any conflicts you resolved and which file you preferred.

Per-file extractions:
"""

GAS_NATURAL_EXTRACTION_PROMPT = """\
You are an expert structured data extractor for Brazilian natural gas engineering projects.

You will receive page images from gas project drawings and memorial-related files, along with \
supplementary OCR text. The images are the PRIMARY source of truth. Use OCR text only to confirm \
or complement what is visible.

Your job is to extract ONLY the fields required by the gas natural memorial v1 contract.

## Where to look for each field

### obra
Look at the title block, cover sheet, or project notes.
- construtora
- nome
- localizacao
- numero_cadastro
- tipo_edificacao
- tipologia
- qtd_apartamentos
- qtd_lojas
- qtd_restaurantes

### crm
Look for the pavimento where the CRM is located.
- pavimento

### dimensionamento
Look for appliance count tables or design notes.
- qtd_fogao
- qtd_aquecedor
- qtd_churrasqueira

### soma
Look for the total utilization points.
- qtd_pontos_de_utilizacao

### ramal
Look for internal primary branch details.
- primario_diametro: preserve the notation exactly as shown in the source, such as `1 1/4"` or `32 mm`.
- primario_material
- primario_pavimento

### valvula
Look for shutoff valve sizing.
- esfera_diametro

### numero
Look for the sheet number associated with the relevant cut/detail.
- prancha

### raiz
- teto_ou_piso

## Rules
- Extract ONLY from evidence visible in the images or OCR text.
- Return null for any field without sufficient evidence.
- NEVER invent or guess values.
- Numeric fields must be numbers, not strings, except `ramal.primario_diametro`, which must preserve the source notation as a string.
- In observacoes, briefly note ambiguities or extraction limitations.
"""

GAS_NATURAL_MERGE_PROMPT = """\
You are merging structured extractions from multiple files of the SAME natural gas project.

Different files may contribute title-block metadata, appliance counts, gas line details, or \
sheet-specific component information.

Your task: produce a SINGLE unified extraction for the gas natural memorial context.

Rules:
- When multiple files provide the SAME field with DIFFERENT values, prefer the value from the \
  most authoritative file for that field.
- When only one file provides a field, use that value.
- Return null only when NO file provided a value.
- In observacoes, note any conflicts you resolved and which file you preferred.

Per-file extractions:
"""

GLP_EXTRACTION_PROMPT = """\
You are an expert structured data extractor for Brazilian GLP (liquefied petroleum gas) engineering projects.

You will receive page images from GLP project drawings and memorial-related files, along with \
supplementary OCR text. The images are the PRIMARY source of truth. Use OCR text only to confirm \
or complement what is visible.

Your job is to extract ONLY the fields required by the GLP memorial v1 contract.

## Where to look for each field

### obra
Look at the title block, cover sheet, or project notes.
- construtora
- nome
- localizacao
- numero_cadastro
- tipo_edificacao
- tipologia
- qtd_apartamentos
- qtd_lojas
- qtd_restaurantes

### abastecimento
Look for the GLP shelter area drawing (abrigo de gás), tank specifications, or supply description.
- qtd_tanques: number of GLP gas SHELTERS (abrigos de gás) in the project — NOT the
  number of P-190 cylinders/recipients inside the shelter. Most projects have ONE
  shelter even when it contains multiple P-190 recipients. Example: if the drawing
  shows ONE shelter ("abrigo de gás") containing TWO P-190 cylinders, return 1, not 2.
  Despite the field name "qtd_tanques", this field counts SHELTERS, not tanks/cylinders.
- pavimento: floor/level where the GLP gas shelter is located

### dimensionamento
Look for appliance count tables or design notes.
- qtd_fogao
- qtd_aquecedor
- qtd_churrasqueira

### soma
Look for the total utilization points.
- qtd_pontos_de_utilizacao

### ramal
Look for internal primary branch details.
- primario_diametro: preserve the notation exactly as shown in the source, such as `1 1/4"` or `32 mm`.
- primario_material
- primario_pavimento

### numero
Look for the sheet number associated with the relevant cut/detail.
- prancha

### raiz
- teto_ou_piso

## Rules
- Extract ONLY from evidence visible in the images or OCR text.
- Return null for any field without sufficient evidence.
- NEVER invent or guess values.
- Numeric fields must be numbers, not strings, except `ramal.primario_diametro`, which must preserve the source notation as a string.
- In observacoes, briefly note ambiguities or extraction limitations.
"""

GLP_MERGE_PROMPT = """\
You are merging structured extractions from multiple files of the SAME GLP project.

Different files may contribute title-block metadata, appliance counts, gas line details, \
tank specifications, or sheet-specific component information.

Your task: produce a SINGLE unified extraction for the GLP memorial context.

Rules:
- When multiple files provide the SAME field with DIFFERENT values, prefer the value from the \
  most authoritative file for that field.
- When only one file provides a field, use that value.
- Return null only when NO file provided a value.
- In observacoes, note any conflicts you resolved and which file you preferred.

Per-file extractions:
"""

GLP_V2_EXTRACTION_PROMPT = """\
You are an expert structured data extractor for Brazilian GLP engineering projects using the \
Memorial GLP **v2** contract (richer evidence, tanks vs shelters, utilization breakdown, diameters).

Images are the PRIMARY source of truth; OCR text supplements them.

## tanques (storage)
- quantidade: count of **installed GLP cylinders/recipients** (e.g. P-190) in the project, NOT legend-only \
symbols. Ignore duplicate depictions of the same physical group in details/sections.
- tipo: tank type label when visible (e.g. P-190).
- capacidade_kg: capacity in kg when explicit.
- qtd_abrigos: count of **shelters / abrigos** housing those recipients — distinct from recipient count. \
Do NOT multiply shelters by cylinders: recipients live inside shelters.

## obra
Same fields as v1. For qtd_apartamentos, count from unit lists / schedules — NEVER set qtd_fogao equal to \
qtd_apartamentos unless a quantitative table explicitly ties stoves to "unidades tipo apartamento" with evidence.

## abastecimento
- pavimento: floor where the GLP installation is located.

## dimensionamento
Per-appliance counts from tables or notes: qtd_fogao, qtd_aquecedor, qtd_churrasqueira, qtd_outros.

## pontos_utilizacao
Extract per type when possible. total_extraido: total from project tables or explicit "pontos" totals when \
they cover all utilization types shown — not raw apartment count.

## diametros
- tubulacao_principal and valvula_esfera: preserve **exact** source notation as strings (e.g. `1 1/4"`, `32 mm`). \
Do not convert units.

## ramal / numero / teto_ou_piso
Same semantics as GLP v1 (`primario_diametro` may still be filled for cross-check).

## Rules
- Return null without evidence; never fabricate numbers to close totals.
- Distinguish **legends, typical details, and symbolic repeats** from physically installed quantities.
- In observacoes, flag ambiguities (e.g. fogão vs apartamentos, conflicting totals).
"""

GLP_V2_MERGE_PROMPT = """\
You are merging GLP **v2** structured extractions from multiple files of the SAME project.

Rules:
- Prefer authoritative sources: title blocks for obra, shelter/tank drawings for tanques, quantitative tables \
for dimensionamento and pontos_utilizacao, line / detail legends for diametros.
- When files disagree on counts, keep both observations in observacoes and choose the most corroborated value.
- Preserve diameter strings verbatim.
- Return null only when NO file provided a value.

Per-file extractions:
"""

GENERIC_CROSS_VALIDATION_PROMPT = """\
You are performing cross-validation for structured memorial extraction candidates from the SAME project.

Rules:
- Choose values ONLY from the provided candidates. Never invent or rewrite a value.
- Repeated identical values across files are stronger evidence, not an error.
- Prefer candidates with higher occurrence_count when the evidence is otherwise equivalent.
- Use source_files, extraction_type, and batch_index as supporting evidence.
- If no candidate is reliable for a field, leave it null.
- Ignore `observacoes` and do not add it to the final output.

Candidate groups by field:
"""


# ── Config ────────────────────────────────────────────────────────────────────


def is_llm_extraction_enabled() -> bool:
    return bool(os.getenv("USE_LLM_EXTRACTION", "").strip())


def _get_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5.4")


def _get_request_timeout() -> float:
    raw = os.getenv("OPENAI_REQUEST_TIMEOUT", "60").strip()
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "Invalid OPENAI_REQUEST_TIMEOUT=%r, falling back to 60.0",
            raw,
        )
        return 60.0
    if value <= 0:
        logger.warning(
            "Non-positive OPENAI_REQUEST_TIMEOUT=%r, falling back to 60.0",
            raw,
        )
        return 60.0
    return value


def _get_client() -> Any:
    from openai import OpenAI

    return OpenAI(timeout=_get_request_timeout())


# ── Vision input builders ─────────────────────────────────────────────────────


def _build_vision_input(source_file: ExtractedSourceFile) -> list[dict[str, Any]]:
    """Build multimodal input: page images + supplementary OCR text."""
    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": EXTRACTION_PROMPT},
    ]

    for page_image in source_file.page_images:
        content.append({
            "type": "input_image",
            "image_url": page_image,
            "detail": "original",
        })

    if source_file.extracted_text.strip():
        content.append({
            "type": "input_text",
            "text": f"Supplementary OCR text from {source_file.original_filename}:\n"
                    f"{source_file.extracted_text}",
        })

    return [{"role": "user", "content": content}]


def _build_telecom_vision_input(source_file: ExtractedSourceFile) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": TELECOM_EXTRACTION_PROMPT},
    ]

    for page_image in source_file.page_images:
        content.append({
            "type": "input_image",
            "image_url": page_image,
            "detail": "original",
        })

    if source_file.extracted_text.strip():
        content.append({
            "type": "input_text",
            "text": f"Supplementary OCR text from {source_file.original_filename}:\n"
                    f"{source_file.extracted_text}",
        })

    return [{"role": "user", "content": content}]


def _build_gas_natural_vision_input(source_file: ExtractedSourceFile) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": GAS_NATURAL_EXTRACTION_PROMPT},
    ]

    for page_image in source_file.page_images:
        content.append({
            "type": "input_image",
            "image_url": page_image,
            "detail": "original",
        })

    if source_file.extracted_text.strip():
        content.append({
            "type": "input_text",
            "text": f"Supplementary OCR text from {source_file.original_filename}:\n"
                    f"{source_file.extracted_text}",
        })

    return [{"role": "user", "content": content}]


def _build_text_only_input(source_file: ExtractedSourceFile) -> list[dict[str, Any]]:
    """Fallback for files without page images (e.g. DOCX)."""
    return [{"role": "user", "content": [
        {"type": "input_text", "text": EXTRACTION_PROMPT},
        {
            "type": "input_text",
            "text": f"=== FILE: {source_file.original_filename} ===\n"
                    f"{source_file.extracted_text}",
        },
    ]}]


def _build_telecom_text_only_input(source_file: ExtractedSourceFile) -> list[dict[str, Any]]:
    return [{"role": "user", "content": [
        {"type": "input_text", "text": TELECOM_EXTRACTION_PROMPT},
        {
            "type": "input_text",
            "text": f"=== FILE: {source_file.original_filename} ===\n"
                    f"{source_file.extracted_text}",
        },
    ]}]


def _build_gas_natural_text_only_input(source_file: ExtractedSourceFile) -> list[dict[str, Any]]:
    return [{"role": "user", "content": [
        {"type": "input_text", "text": GAS_NATURAL_EXTRACTION_PROMPT},
        {
            "type": "input_text",
            "text": f"=== FILE: {source_file.original_filename} ===\n"
                    f"{source_file.extracted_text}",
        },
    ]}]


def _build_glp_vision_input(source_file: ExtractedSourceFile) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": GLP_EXTRACTION_PROMPT},
    ]

    for page_image in source_file.page_images:
        content.append({
            "type": "input_image",
            "image_url": page_image,
            "detail": "original",
        })

    if source_file.extracted_text.strip():
        content.append({
            "type": "input_text",
            "text": f"Supplementary OCR text from {source_file.original_filename}:\n"
                    f"{source_file.extracted_text}",
        })

    return [{"role": "user", "content": content}]


def _build_glp_text_only_input(source_file: ExtractedSourceFile) -> list[dict[str, Any]]:
    return [{"role": "user", "content": [
        {"type": "input_text", "text": GLP_EXTRACTION_PROMPT},
        {
            "type": "input_text",
            "text": f"=== FILE: {source_file.original_filename} ===\n"
                    f"{source_file.extracted_text}",
        },
    ]}]


def _build_glp_combined_text_input(
    source_files: list[ExtractedSourceFile],
) -> list[dict[str, Any]]:
    return _build_combined_text_input(source_files, GLP_EXTRACTION_PROMPT)


def _build_glp_v2_vision_input(source_file: ExtractedSourceFile) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {"type": "input_text", "text": GLP_V2_EXTRACTION_PROMPT},
    ]

    for page_image in source_file.page_images:
        content.append({
            "type": "input_image",
            "image_url": page_image,
            "detail": "original",
        })

    if source_file.extracted_text.strip():
        content.append({
            "type": "input_text",
            "text": f"Supplementary OCR text from {source_file.original_filename}:\n"
                    f"{source_file.extracted_text}",
        })

    return [{"role": "user", "content": content}]


def _build_glp_v2_text_only_input(source_file: ExtractedSourceFile) -> list[dict[str, Any]]:
    return [{"role": "user", "content": [
        {"type": "input_text", "text": GLP_V2_EXTRACTION_PROMPT},
        {
            "type": "input_text",
            "text": f"=== FILE: {source_file.original_filename} ===\n"
                    f"{source_file.extracted_text}",
        },
    ]}]


def _build_glp_v2_combined_text_input(
    source_files: list[ExtractedSourceFile],
) -> list[dict[str, Any]]:
    return _build_combined_text_input(source_files, GLP_V2_EXTRACTION_PROMPT)


def _build_combined_text_input(
    source_files: list[ExtractedSourceFile],
    prompt: str,
) -> list[dict[str, Any]]:
    sections = [
        f"=== FILE: {source_file.original_filename} ===\n{source_file.extracted_text}"
        for source_file in source_files
        if source_file.extracted_text.strip()
    ]
    return [{"role": "user", "content": [
        {"type": "input_text", "text": prompt},
        {"type": "input_text", "text": "\n\n".join(sections)},
    ]}]


def _build_merge_input(
    per_file_results: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    sections = []
    for filename, extraction in per_file_results:
        sections.append(f"=== {filename} ===\n{json.dumps(extraction, ensure_ascii=False, indent=2)}")

    return [{"role": "user", "content": [
        {"type": "input_text", "text": MERGE_PROMPT + "\n\n".join(sections)},
    ]}]


def _build_telecom_merge_input(
    per_file_results: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    sections = []
    for filename, extraction in per_file_results:
        sections.append(f"=== {filename} ===\n{json.dumps(extraction, ensure_ascii=False, indent=2)}")

    return [{"role": "user", "content": [
        {"type": "input_text", "text": TELECOM_MERGE_PROMPT + "\n\n".join(sections)},
    ]}]


def _build_gas_natural_merge_input(
    per_file_results: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    sections = []
    for filename, extraction in per_file_results:
        sections.append(f"=== {filename} ===\n{json.dumps(extraction, ensure_ascii=False, indent=2)}")

    return [{"role": "user", "content": [
        {"type": "input_text", "text": GAS_NATURAL_MERGE_PROMPT + "\n\n".join(sections)},
    ]}]


def _build_glp_merge_input(
    per_file_results: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    sections = []
    for filename, extraction in per_file_results:
        sections.append(f"=== {filename} ===\n{json.dumps(extraction, ensure_ascii=False, indent=2)}")

    return [{"role": "user", "content": [
        {"type": "input_text", "text": GLP_MERGE_PROMPT + "\n\n".join(sections)},
    ]}]


def _build_glp_v2_merge_input(
    per_file_results: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    sections = []
    for filename, extraction in per_file_results:
        sections.append(f"=== {filename} ===\n{json.dumps(extraction, ensure_ascii=False, indent=2)}")

    return [{"role": "user", "content": [
        {"type": "input_text", "text": GLP_V2_MERGE_PROMPT + "\n\n".join(sections)},
    ]}]


# ── Extraction ────────────────────────────────────────────────────────────────


def _count_non_null_fields(extraction: dict[str, Any]) -> int:
    return sum(
        1
        for _field_path, value in _iter_non_null_fields(extraction)
        if value is not None
    )


def _extract_single_file(
    client: Any,
    model: str,
    source_file: ExtractedSourceFile,
) -> dict[str, Any]:
    has_images = bool(source_file.page_images)
    input_messages = (
        _build_vision_input(source_file) if has_images
        else _build_text_only_input(source_file)
    )

    kwargs: dict[str, Any] = {
        "model": model,
        "input": input_messages,
        "text_format": LLMExtraction,
    }
    if has_images:
        kwargs["reasoning"] = {"effort": "high"}

    response = client.responses.parse(**kwargs)
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _extract_telecom_single_file(
    client: Any,
    model: str,
    source_file: ExtractedSourceFile,
) -> dict[str, Any]:
    has_images = bool(source_file.page_images)
    input_messages = (
        _build_telecom_vision_input(source_file) if has_images
        else _build_telecom_text_only_input(source_file)
    )

    kwargs: dict[str, Any] = {
        "model": model,
        "input": input_messages,
        "text_format": TelecomLLMExtraction,
    }
    if has_images:
        kwargs["reasoning"] = {"effort": "high"}

    response = client.responses.parse(**kwargs)
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _extract_gas_natural_single_file(
    client: Any,
    model: str,
    source_file: ExtractedSourceFile,
) -> dict[str, Any]:
    has_images = bool(source_file.page_images)
    input_messages = (
        _build_gas_natural_vision_input(source_file) if has_images
        else _build_gas_natural_text_only_input(source_file)
    )

    kwargs: dict[str, Any] = {
        "model": model,
        "input": input_messages,
        "text_format": GasNaturalLLMExtraction,
    }
    if has_images:
        kwargs["reasoning"] = {"effort": "high"}

    response = client.responses.parse(**kwargs)
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _has_rich_text(source_file: ExtractedSourceFile) -> bool:
    return (
        bool(source_file.extracted_text.strip())
        and len(source_file.extracted_text) >= RICH_TEXT_ONLY_THRESHOLD
    )


def _merge_with_llm(
    client: Any,
    model: str,
    per_file_results: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Use LLM to intelligently merge per-file extractions."""
    response = client.responses.parse(
        model=model,
        input=_build_merge_input(per_file_results),
        text_format=LLMExtraction,
    )
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _merge_telecom_with_llm(
    client: Any,
    model: str,
    per_file_results: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    response = client.responses.parse(
        model=model,
        input=_build_telecom_merge_input(per_file_results),
        text_format=TelecomLLMExtraction,
    )
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _merge_gas_natural_with_llm(
    client: Any,
    model: str,
    per_file_results: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    response = client.responses.parse(
        model=model,
        input=_build_gas_natural_merge_input(per_file_results),
        text_format=GasNaturalLLMExtraction,
    )
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _extract_glp_single_file(
    client: Any,
    model: str,
    source_file: ExtractedSourceFile,
) -> dict[str, Any]:
    has_images = bool(source_file.page_images)
    use_text_only = bool(source_file.extracted_text.strip()) and len(source_file.extracted_text) >= GLP_TEXT_ONLY_THRESHOLD
    input_messages = (
        _build_glp_text_only_input(source_file)
        if use_text_only or not has_images
        else _build_glp_vision_input(source_file)
    )

    kwargs: dict[str, Any] = {
        "model": model,
        "input": input_messages,
        "text_format": GlpLLMExtraction,
    }
    if has_images and not use_text_only:
        kwargs["reasoning"] = {"effort": "high"}

    response = client.responses.parse(**kwargs)
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _extract_glp_v2_single_file(
    client: Any,
    model: str,
    source_file: ExtractedSourceFile,
) -> dict[str, Any]:
    has_images = bool(source_file.page_images)
    use_text_only = bool(source_file.extracted_text.strip()) and len(source_file.extracted_text) >= GLP_TEXT_ONLY_THRESHOLD
    input_messages = (
        _build_glp_v2_text_only_input(source_file)
        if use_text_only or not has_images
        else _build_glp_v2_vision_input(source_file)
    )

    kwargs: dict[str, Any] = {
        "model": model,
        "input": input_messages,
        "text_format": GlpV2LLMExtraction,
    }
    if has_images and not use_text_only:
        kwargs["reasoning"] = {"effort": "high"}

    response = client.responses.parse(**kwargs)
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _extract_glp_combined_text(
    client: Any,
    model: str,
    source_files: list[ExtractedSourceFile],
) -> dict[str, Any]:
    response = client.responses.parse(
        model=model,
        input=_build_glp_combined_text_input(source_files),
        text_format=GlpLLMExtraction,
    )
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _merge_glp_with_llm(
    client: Any,
    model: str,
    per_file_results: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    response = client.responses.parse(
        model=model,
        input=_build_glp_merge_input(per_file_results),
        text_format=GlpLLMExtraction,
    )
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _merge_glp_v2_with_llm(
    client: Any,
    model: str,
    per_file_results: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    response = client.responses.parse(
        model=model,
        input=_build_glp_v2_merge_input(per_file_results),
        text_format=GlpV2LLMExtraction,
    )
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _cross_validate_with_llm(
    client: Any,
    model: str,
    strategy: ExtractionStrategy,
    candidate_groups: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    response = client.responses.parse(
        model=model,
        input=_build_cross_validation_input(strategy, candidate_groups),
        text_format=strategy.text_format,
    )
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _get_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r, using default=%d", name, raw, default)
        return default
    if value <= 0:
        logger.warning("Non-positive integer for %s=%r, using default=%d", name, raw, default)
        return default
    return value


def _get_batch_size() -> int:
    return _get_positive_int_env("LLM_EXTRACTION_BATCH_SIZE", 5)


def _get_max_concurrency() -> int:
    return _get_positive_int_env("LLM_EXTRACTION_MAX_CONCURRENCY", 5)


def _chunk_source_files(
    source_files: list[ExtractedSourceFile],
    batch_size: int,
) -> list[list[ExtractedSourceFile]]:
    return [
        source_files[index:index + batch_size]
        for index in range(0, len(source_files), batch_size)
    ]


def _iter_non_null_fields(
    payload: dict[str, Any],
    prefix: str = "",
):
    for key, value in payload.items():
        if key == "observacoes":
            continue
        field_path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _iter_non_null_fields(value, field_path)
            continue
        if value is not None:
            yield field_path, value


def _set_field_value(context: dict[str, Any], field_path: str, value: Any) -> None:
    parts = field_path.split(".")
    cursor = context
    for part in parts[:-1]:
        next_cursor = cursor.get(part)
        if not isinstance(next_cursor, dict):
            next_cursor = {}
            cursor[part] = next_cursor
        cursor = next_cursor
    cursor[parts[-1]] = value


def _get_field_value(context: dict[str, Any], field_path: str) -> Any:
    parts = field_path.split(".")
    cursor: Any = context
    for part in parts:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(part)
    return cursor


def _stable_value_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _build_cross_validation_input(
    strategy: ExtractionStrategy,
    candidate_groups: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    sections = []
    for field_path, candidates in sorted(candidate_groups.items()):
        sections.append(
            f"=== {field_path} ===\n{json.dumps(candidates, ensure_ascii=False, indent=2)}"
        )
    prompt = (
        GENERIC_CROSS_VALIDATION_PROMPT
        + "\n"
        + strategy.cross_validation_intro.strip()
        + "\n\n"
        + "\n\n".join(sections)
    )
    return [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]


def _extract_file_with_metadata(
    strategy: ExtractionStrategy,
    client: Any,
    model: str,
    source_file: ExtractedSourceFile,
) -> BatchFileExtractionResult:
    payload = strategy.single_file_extractor(client, model, source_file)
    extraction_type = "vision" if source_file.page_images and not _has_rich_text(source_file) else "text"
    return BatchFileExtractionResult(
        filename=source_file.original_filename,
        extraction_type=extraction_type,
        payload=payload,
    )


def _extract_batch(
    strategy: ExtractionStrategy,
    client: Any,
    model: str,
    batch_index: int,
    source_files: list[ExtractedSourceFile],
    max_concurrency: int,
) -> BatchExtractionResult:
    per_file_results: list[BatchFileExtractionResult] = []
    with ThreadPoolExecutor(max_workers=min(max_concurrency, len(source_files))) as executor:
        future_to_file = {
            executor.submit(
                _extract_file_with_metadata, strategy, client, model, source_file
            ): source_file
            for source_file in source_files
        }
        for future, source_file in future_to_file.items():
            try:
                result = future.result()
            except Exception as exc:
                logger.warning(
                    "%s LLM extraction failed for file %s (batch=%d): error_type=%s",
                    strategy.name,
                    source_file.original_filename,
                    batch_index,
                    type(exc).__name__,
                )
                per_file_results.append(
                    BatchFileExtractionResult(
                        filename=source_file.original_filename,
                        extraction_type="error",
                        payload={},
                        error=str(exc),
                    )
                )
                continue
            if result.payload:
                per_file_results.append(result)

    if not per_file_results:
        return BatchExtractionResult(
            batch_index=batch_index,
            files=[source_file.original_filename for source_file in source_files],
            per_file_results=[],
            merged_payload={},
        )

    if len(per_file_results) == 1:
        merged_payload = per_file_results[0].payload
    else:
        merged_payload = strategy.batch_merger(
            client,
            model,
            [(result.filename, result.payload) for result in per_file_results],
        )

    return BatchExtractionResult(
        batch_index=batch_index,
        files=[source_file.original_filename for source_file in source_files],
        per_file_results=per_file_results,
        merged_payload=merged_payload,
    )


def _build_candidate_groups(
    batch_results: list[BatchExtractionResult],
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_candidates = 0

    for batch in batch_results:
        supporting_values: dict[str, dict[str, list[BatchFileExtractionResult]]] = defaultdict(lambda: defaultdict(list))
        for per_file in batch.per_file_results:
            for field_path, value in _iter_non_null_fields(per_file.payload):
                supporting_values[field_path][_stable_value_key(value)].append(per_file)

        for field_path, value in _iter_non_null_fields(batch.merged_payload):
            value_key = _stable_value_key(value)
            supporting_files = supporting_values.get(field_path, {}).get(value_key, [])
            grouped[field_path].append({
                "value": value,
                "source_files": [item.filename for item in supporting_files] or batch.files,
                "batch_index": batch.batch_index,
                "extraction_type": (
                    "vision"
                    if any(item.extraction_type == "vision" for item in supporting_files)
                    else "text"
                ),
                "occurrence_count": len(supporting_files) or 1,
            })
            total_candidates += 1

    for field_path, candidates in grouped.items():
        occurrences: dict[str, int] = defaultdict(int)
        for candidate in candidates:
            occurrences[_stable_value_key(candidate["value"])] += int(candidate["occurrence_count"])
        for candidate in candidates:
            candidate["occurrence_count"] = occurrences[_stable_value_key(candidate["value"])]

    return dict(grouped), total_candidates


def _apply_validated_selection(
    candidate_groups: dict[str, list[dict[str, Any]]],
    validated_context: dict[str, Any],
) -> tuple[dict[str, Any], set[str]]:
    context: dict[str, Any] = {}
    resolved_fields: set[str] = set()

    for field_path, candidates in candidate_groups.items():
        selected_value = _get_field_value(validated_context, field_path)
        if selected_value is None:
            continue
        candidate_values = {_stable_value_key(candidate["value"]) for candidate in candidates}
        if _stable_value_key(selected_value) not in candidate_values:
            logger.warning("Ignoring cross-validation value not present in candidates: %s", field_path)
            continue
        _set_field_value(context, field_path, selected_value)
        resolved_fields.add(field_path)

    return context, resolved_fields


def _deterministic_fallback_from_candidates(
    candidate_groups: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    context: dict[str, Any] = {}
    conflicts: list[dict[str, Any]] = []
    resolved_fields: set[str] = set()

    for field_path, candidates in candidate_groups.items():
        if not candidates:
            continue
        grouped_by_value: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            key = _stable_value_key(candidate["value"])
            current = grouped_by_value.get(key)
            if current is None or candidate["occurrence_count"] > current["occurrence_count"]:
                grouped_by_value[key] = candidate

        ordered = sorted(
            grouped_by_value.values(),
            key=lambda item: (-int(item["occurrence_count"]), item["batch_index"]),
        )
        if len(ordered) == 1:
            winner = ordered[0]
            _set_field_value(context, field_path, winner["value"])
            resolved_fields.add(field_path)
            continue

        top = ordered[0]
        second = ordered[1]
        if int(top["occurrence_count"]) > int(second["occurrence_count"]):
            _set_field_value(context, field_path, top["value"])
            resolved_fields.add(field_path)
            conflicts.append({
                "field_path": field_path,
                "status": "resolved_by_frequency",
                "selected_value": top["value"],
                "candidates": ordered,
            })
            continue

        conflicts.append({
            "field_path": field_path,
            "status": "unresolved",
            "selected_value": None,
            "candidates": ordered,
        })

    return context, conflicts, resolved_fields


def _build_cross_validation_summary(
    batch_size: int,
    batch_count: int,
    candidate_count: int,
    resolved_fields: set[str],
    conflicts: list[dict[str, Any]],
    fallback_used: bool,
) -> dict[str, Any]:
    return {
        "batch_size": batch_size,
        "batch_count": batch_count,
        "candidate_count": candidate_count,
        "resolved_fields": sorted(resolved_fields),
        "conflicts": conflicts,
        "fallback_used": fallback_used,
    }


def _run_llm_extraction(
    source_files: list[ExtractedSourceFile],
    strategy: ExtractionStrategy,
) -> LLMExtractionRunResult:
    usable_files = [
        source_file
        for source_file in source_files
        if source_file.extracted_text.strip() or source_file.page_images
    ]
    if not usable_files:
        logger.info("No extractable content in %s source files, skipping LLM", strategy.name)
        return LLMExtractionRunResult(context={})

    client = _get_client()
    model = _get_model()
    batch_size = _get_batch_size()
    max_concurrency = _get_max_concurrency()
    batches = _chunk_source_files(usable_files, batch_size)
    logger.info(
        "%s LLM extraction: model=%s, files=%d, batches=%d, batch_size=%d, concurrency=%d",
        strategy.name,
        model,
        len(usable_files),
        len(batches),
        batch_size,
        max_concurrency,
    )

    t0 = time.monotonic()
    batch_results: list[BatchExtractionResult] = []
    for batch_index, batch in enumerate(batches):
        batch_result = _extract_batch(
            strategy,
            client,
            model,
            batch_index,
            batch,
            max_concurrency,
        )
        batch_results.append(batch_result)
        logger.info(
            "  %s batch %d/%d: files=%d, fields=%d",
            strategy.name,
            batch_index + 1,
            len(batches),
            len(batch),
            _count_non_null_fields(batch_result.merged_payload),
        )

    non_empty_batches = [batch for batch in batch_results if batch.merged_payload]
    if not non_empty_batches:
        logger.warning("%s LLM extraction returned no results from any batch", strategy.name)
        return LLMExtractionRunResult(context={})

    candidate_groups, candidate_count = _build_candidate_groups(non_empty_batches)
    fallback_used = False
    conflicts: list[dict[str, Any]] = []
    resolved_fields: set[str] = set()

    if len(non_empty_batches) == 1:
        final_context = non_empty_batches[0].merged_payload
        resolved_fields = {field_path for field_path, _ in _iter_non_null_fields(final_context)}
    else:
        try:
            validated_context = _cross_validate_with_llm(
                client,
                model,
                strategy,
                candidate_groups,
            )
            final_context, resolved_fields = _apply_validated_selection(
                candidate_groups,
                validated_context,
            )
        except Exception:
            logger.exception("%s cross-validation failed; applying deterministic fallback", strategy.name)
            final_context = {}

        fallback_context, conflicts, fallback_resolved = _deterministic_fallback_from_candidates(
            candidate_groups
        )
        for field_path, value in _iter_non_null_fields(fallback_context):
            if _get_field_value(final_context, field_path) is None:
                _set_field_value(final_context, field_path, value)
        if conflicts or fallback_resolved - resolved_fields:
            fallback_used = True
        resolved_fields |= fallback_resolved

    final_context.pop("observacoes", None)
    elapsed = time.monotonic() - t0
    logger.info(
        "%s LLM extraction complete: fields=%d, elapsed=%.1fs",
        strategy.name,
        _count_non_null_fields(final_context),
        elapsed,
    )
    return LLMExtractionRunResult(
        context=final_context,
        cross_validation=_build_cross_validation_summary(
            batch_size=batch_size,
            batch_count=len(batches),
            candidate_count=candidate_count,
            resolved_fields=resolved_fields,
            conflicts=conflicts,
            fallback_used=fallback_used,
        ),
    )


def _first_non_null_merge(partials: list[dict[str, Any]]) -> dict[str, Any]:
    """Simple deterministic fallback: first non-null value wins per field."""
    merged: dict[str, Any] = {}
    for partial in partials:
        for section_key, section_value in partial.items():
            if section_key == "observacoes":
                continue
            if not isinstance(section_value, dict):
                continue
            if section_key not in merged:
                merged[section_key] = {}
            for field_key, field_value in section_value.items():
                if merged[section_key].get(field_key) is None and field_value is not None:
                    merged[section_key][field_key] = field_value
    return merged


ELETRICO_STRATEGY = ExtractionStrategy(
    name="Eletrico",
    cross_validation_intro=(
        "Return the final electrical memorial extraction using only candidate values. "
        "Prefer title block evidence for obra, single-line diagrams for energia/mt, grounding "
        "details for aterramento, and dedicated panels or legends for nao_inclusos."
    ),
    text_format=LLMExtraction,
    single_file_extractor=_extract_single_file,
    batch_merger=_merge_with_llm,
)

TELECOM_STRATEGY = ExtractionStrategy(
    name="Telecom",
    cross_validation_intro=(
        "Return the final telecom memorial extraction using only candidate values. "
        "Prefer cover sheets, title blocks, and general notes when project metadata conflicts."
    ),
    text_format=TelecomLLMExtraction,
    single_file_extractor=_extract_telecom_single_file,
    batch_merger=_merge_telecom_with_llm,
)

GAS_NATURAL_STRATEGY = ExtractionStrategy(
    name="Gas natural",
    cross_validation_intro=(
        "Return the final natural gas memorial extraction using only candidate values. "
        "Prefer title blocks for obra, appliance tables for dimensionamento/soma, and line "
        "details for ramal, valvula, numero, and teto_ou_piso."
    ),
    text_format=GasNaturalLLMExtraction,
    single_file_extractor=_extract_gas_natural_single_file,
    batch_merger=_merge_gas_natural_with_llm,
)

GLP_STRATEGY = ExtractionStrategy(
    name="GLP",
    cross_validation_intro=(
        "Return the final GLP memorial extraction using only candidate values. "
        "Prefer title blocks for obra, tank-area drawings for abastecimento, appliance tables "
        "for dimensionamento/soma, and line details for ramal, numero, and teto_ou_piso."
    ),
    text_format=GlpLLMExtraction,
    single_file_extractor=_extract_glp_single_file,
    batch_merger=_merge_glp_with_llm,
)

GLP_V2_STRATEGY = ExtractionStrategy(
    name="GLP_v2",
    cross_validation_intro=(
        "Return the final GLP memorial v2 extraction using only candidate values. "
        "Prefer shelter and recipient drawings for tanques, quantitative tables for pontos_utilizacao, "
        "unit schedules for obra.qtd_apartamentos, and explicit pipe callouts for diametros strings."
    ),
    text_format=GlpV2LLMExtraction,
    single_file_extractor=_extract_glp_v2_single_file,
    batch_merger=_merge_glp_v2_with_llm,
)


def extract_with_llm_result(source_files: list[ExtractedSourceFile]) -> LLMExtractionRunResult:
    if not is_llm_extraction_enabled():
        logger.debug("LLM extraction disabled, skipping")
        return LLMExtractionRunResult(context={})
    return _run_llm_extraction(source_files, ELETRICO_STRATEGY)


def extract_with_llm(source_files: list[ExtractedSourceFile]) -> dict[str, Any]:
    """Vision-first extraction: send page images + text to GPT for structured extraction."""
    return extract_with_llm_result(source_files).context


def extract_telecom_with_llm_result(
    source_files: list[ExtractedSourceFile],
) -> LLMExtractionRunResult:
    if not is_llm_extraction_enabled():
        logger.debug("Telecom LLM extraction disabled, skipping")
        return LLMExtractionRunResult(context={})
    return _run_llm_extraction(source_files, TELECOM_STRATEGY)


def extract_telecom_with_llm(source_files: list[ExtractedSourceFile]) -> dict[str, Any]:
    """Vision-first extraction for telecom memorial fields only."""
    return extract_telecom_with_llm_result(source_files).context


def extract_gas_natural_with_llm_result(
    source_files: list[ExtractedSourceFile],
) -> LLMExtractionRunResult:
    if not is_llm_extraction_enabled():
        logger.debug("Gas natural LLM extraction disabled, skipping")
        return LLMExtractionRunResult(context={})
    return _run_llm_extraction(source_files, GAS_NATURAL_STRATEGY)


def extract_gas_natural_with_llm(source_files: list[ExtractedSourceFile]) -> dict[str, Any]:
    """Vision-first extraction for gas natural memorial fields only."""
    return extract_gas_natural_with_llm_result(source_files).context


def extract_glp_with_llm_result(
    source_files: list[ExtractedSourceFile],
) -> LLMExtractionRunResult:
    if not is_llm_extraction_enabled():
        logger.debug("GLP LLM extraction disabled, skipping")
        return LLMExtractionRunResult(context={})
    return _run_llm_extraction(source_files, GLP_STRATEGY)


def extract_glp_with_llm(source_files: list[ExtractedSourceFile]) -> dict[str, Any]:
    """Vision-first extraction for GLP memorial fields only."""
    return extract_glp_with_llm_result(source_files).context


def extract_glp_v2_with_llm_result(
    source_files: list[ExtractedSourceFile],
) -> LLMExtractionRunResult:
    if not is_llm_extraction_enabled():
        logger.debug("GLP v2 LLM extraction disabled, skipping")
        return LLMExtractionRunResult(context={})
    return _run_llm_extraction(source_files, GLP_V2_STRATEGY)


def extract_glp_v2_with_llm(source_files: list[ExtractedSourceFile]) -> dict[str, Any]:
    """Vision-first extraction for GLP memorial v2 structured contract."""
    return extract_glp_v2_with_llm_result(source_files).context
