from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from pydantic import BaseModel

from app.services.project_extractor import ExtractedSourceFile

logger = logging.getLogger(__name__)
RICH_TEXT_ONLY_THRESHOLD = 4000
GLP_TEXT_ONLY_THRESHOLD = RICH_TEXT_ONLY_THRESHOLD


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
Look for the GLP tank area drawing, tank specifications, or supply description.
- qtd_tanques: number of GLP tanks (typically P-190 type)
- pavimento: floor/level where the GLP tank shelter is located

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


# ── Config ────────────────────────────────────────────────────────────────────


def is_llm_extraction_enabled() -> bool:
    return bool(os.getenv("USE_LLM_EXTRACTION", "").strip())


def _get_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5.4")


def _get_client() -> Any:
    from openai import OpenAI

    return OpenAI()


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


# ── Extraction ────────────────────────────────────────────────────────────────


def _count_non_null_fields(extraction: dict[str, Any]) -> int:
    return sum(
        1 for section in extraction.values()
        if isinstance(section, dict)
        for v in section.values()
        if v is not None
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


def _should_use_combined_text_extraction(
    source_files: list[ExtractedSourceFile],
) -> bool:
    return len(source_files) > 1 and all(_has_rich_text(sf) for sf in source_files)


def _extract_combined_text(
    client: Any,
    model: str,
    source_files: list[ExtractedSourceFile],
    prompt: str,
    text_format: type[BaseModel],
) -> dict[str, Any]:
    response = client.responses.parse(
        model=model,
        input=_build_combined_text_input(source_files, prompt),
        text_format=text_format,
    )
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


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


def extract_with_llm(source_files: list[ExtractedSourceFile]) -> dict[str, Any]:
    """Vision-first extraction: send page images + text to GPT for structured extraction."""
    if not is_llm_extraction_enabled():
        logger.debug("LLM extraction disabled, skipping")
        return {}

    usable_files = [
        sf for sf in source_files
        if sf.extracted_text.strip() or sf.page_images
    ]
    if not usable_files:
        logger.info("No extractable content in source files, skipping LLM")
        return {}

    client = _get_client()
    model = _get_model()
    logger.info(
        "LLM vision extraction: model=%s, files=%d",
        model, len(usable_files),
    )

    t0 = time.monotonic()
    if _should_use_combined_text_extraction(usable_files):
        logger.info("Using single combined text extraction for %d files", len(usable_files))
        merged = _extract_combined_text(
            client,
            model,
            usable_files,
            EXTRACTION_PROMPT,
            LLMExtraction,
        )
        merged.pop("observacoes", None)
        elapsed = time.monotonic() - t0
        logger.info(
            "Combined text extraction complete: fields=%d, elapsed=%.1fs",
            _count_non_null_fields(merged),
            elapsed,
        )
        return merged

    per_file_results: list[tuple[str, dict[str, Any]]] = []

    for sf in usable_files:
        result = _extract_single_file(client, model, sf)
        if result:
            per_file_results.append((sf.original_filename, result))
            logger.info("  %s: %d fields extracted", sf.original_filename, _count_non_null_fields(result))

    if not per_file_results:
        logger.warning("LLM extraction returned no results from any file")
        return {}

    if len(per_file_results) == 1:
        merged = per_file_results[0][1]
    else:
        logger.info("Merging %d per-file extractions with LLM", len(per_file_results))
        merged = _merge_with_llm(client, model, per_file_results)

    merged.pop("observacoes", None)
    elapsed = time.monotonic() - t0
    logger.info("LLM extraction complete: fields=%d, elapsed=%.1fs", _count_non_null_fields(merged), elapsed)

    return merged


def extract_telecom_with_llm(source_files: list[ExtractedSourceFile]) -> dict[str, Any]:
    """Vision-first extraction for telecom memorial fields only."""
    if not is_llm_extraction_enabled():
        logger.debug("Telecom LLM extraction disabled, skipping")
        return {}

    usable_files = [
        sf for sf in source_files
        if sf.extracted_text.strip() or sf.page_images
    ]
    if not usable_files:
        logger.info("No extractable content in telecom source files, skipping LLM")
        return {}

    client = _get_client()
    model = _get_model()
    logger.info(
        "Telecom LLM vision extraction: model=%s, files=%d",
        model, len(usable_files),
    )

    t0 = time.monotonic()
    if _should_use_combined_text_extraction(usable_files):
        logger.info("Using single combined telecom text extraction for %d files", len(usable_files))
        merged = _extract_combined_text(
            client,
            model,
            usable_files,
            TELECOM_EXTRACTION_PROMPT,
            TelecomLLMExtraction,
        )
        merged.pop("observacoes", None)
        elapsed = time.monotonic() - t0
        logger.info(
            "Telecom combined text extraction complete: fields=%d, elapsed=%.1fs",
            _count_non_null_fields(merged),
            elapsed,
        )
        return merged

    per_file_results: list[tuple[str, dict[str, Any]]] = []

    for sf in usable_files:
        result = _extract_telecom_single_file(client, model, sf)
        if result:
            per_file_results.append((sf.original_filename, result))
            logger.info(
                "  telecom %s: %d fields extracted",
                sf.original_filename,
                _count_non_null_fields(result),
            )

    if not per_file_results:
        logger.warning("Telecom LLM extraction returned no results from any file")
        return {}

    if len(per_file_results) == 1:
        merged = per_file_results[0][1]
    else:
        logger.info("Merging %d telecom per-file extractions with LLM", len(per_file_results))
        merged = _merge_telecom_with_llm(client, model, per_file_results)

    merged.pop("observacoes", None)
    elapsed = time.monotonic() - t0
    logger.info(
        "Telecom LLM extraction complete: fields=%d, elapsed=%.1fs",
        _count_non_null_fields(merged),
        elapsed,
    )

    return merged


def extract_gas_natural_with_llm(source_files: list[ExtractedSourceFile]) -> dict[str, Any]:
    """Vision-first extraction for gas natural memorial fields only."""
    if not is_llm_extraction_enabled():
        logger.debug("Gas natural LLM extraction disabled, skipping")
        return {}

    usable_files = [
        sf for sf in source_files
        if sf.extracted_text.strip() or sf.page_images
    ]
    if not usable_files:
        logger.info("No extractable content in gas natural source files, skipping LLM")
        return {}

    client = _get_client()
    model = _get_model()
    logger.info(
        "Gas natural LLM vision extraction: model=%s, files=%d",
        model, len(usable_files),
    )

    t0 = time.monotonic()
    if _should_use_combined_text_extraction(usable_files) and not any(
        sf.page_images for sf in usable_files
    ):
        logger.info("Using single combined gas natural text extraction for %d files", len(usable_files))
        merged = _extract_combined_text(
            client,
            model,
            usable_files,
            GAS_NATURAL_EXTRACTION_PROMPT,
            GasNaturalLLMExtraction,
        )
        merged.pop("observacoes", None)
        elapsed = time.monotonic() - t0
        logger.info(
            "Gas natural combined text extraction complete: fields=%d, elapsed=%.1fs",
            _count_non_null_fields(merged),
            elapsed,
        )
        return merged

    per_file_results: list[tuple[str, dict[str, Any]]] = []

    for sf in usable_files:
        result = _extract_gas_natural_single_file(client, model, sf)
        if result:
            per_file_results.append((sf.original_filename, result))
            logger.info(
                "  gas natural %s: %d fields extracted",
                sf.original_filename,
                _count_non_null_fields(result),
            )

    if not per_file_results:
        logger.warning("Gas natural LLM extraction returned no results from any file")
        return {}

    if len(per_file_results) == 1:
        merged = per_file_results[0][1]
    else:
        logger.info("Merging %d gas natural per-file extractions with LLM", len(per_file_results))
        merged = _merge_gas_natural_with_llm(client, model, per_file_results)

    merged.pop("observacoes", None)
    elapsed = time.monotonic() - t0
    logger.info(
        "Gas natural LLM extraction complete: fields=%d, elapsed=%.1fs",
        _count_non_null_fields(merged),
        elapsed,
    )

    return merged


def extract_glp_with_llm(source_files: list[ExtractedSourceFile]) -> dict[str, Any]:
    """Vision-first extraction for GLP memorial fields only."""
    if not is_llm_extraction_enabled():
        logger.debug("GLP LLM extraction disabled, skipping")
        return {}

    usable_files = [
        sf for sf in source_files
        if sf.extracted_text.strip() or sf.page_images
    ]
    if not usable_files:
        logger.info("No extractable content in GLP source files, skipping LLM")
        return {}

    client = _get_client()
    model = _get_model()
    logger.info("GLP LLM vision extraction: model=%s, files=%d", model, len(usable_files))

    t0 = time.monotonic()
    if len(usable_files) > 1 and all(
        sf.extracted_text.strip() and len(sf.extracted_text) >= GLP_TEXT_ONLY_THRESHOLD
        for sf in usable_files
    ):
        logger.info("Using single combined GLP text extraction for %d files", len(usable_files))
        merged = _extract_glp_combined_text(client, model, usable_files)
        merged.pop("observacoes", None)
        elapsed = time.monotonic() - t0
        logger.info("GLP combined text extraction complete: fields=%d, elapsed=%.1fs", _count_non_null_fields(merged), elapsed)
        return merged

    per_file_results: list[tuple[str, dict[str, Any]]] = []

    for sf in usable_files:
        result = _extract_glp_single_file(client, model, sf)
        if result:
            per_file_results.append((sf.original_filename, result))
            logger.info("  glp %s: %d fields extracted", sf.original_filename, _count_non_null_fields(result))

    if not per_file_results:
        logger.warning("GLP LLM extraction returned no results from any file")
        return {}

    if len(per_file_results) == 1:
        merged = per_file_results[0][1]
    else:
        logger.info("Merging %d GLP per-file extractions with LLM", len(per_file_results))
        merged = _merge_glp_with_llm(client, model, per_file_results)

    merged.pop("observacoes", None)
    elapsed = time.monotonic() - t0
    logger.info("GLP LLM extraction complete: fields=%d, elapsed=%.1fs", _count_non_null_fields(merged), elapsed)

    return merged
