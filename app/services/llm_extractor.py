from __future__ import annotations

import logging
import os
import time
from typing import Any

from pydantic import BaseModel

from app.services.project_extractor import ExtractedSourceFile

logger = logging.getLogger(__name__)

BATCH_SIZE = 1
RATE_LIMIT_WAIT_SECONDS = 30


# ── Schema de extração ───────────────────────────────────────────────────────

class ObraExtraction(BaseModel):
    construtora: str | None = None
    nome: str | None = None
    localizacao: str | None = None
    numero_cadastro: str | None = None
    tipo_edificacao: str | None = None
    tipologia: str | None = None
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
    secao_cabo_mm2: float | None = None

class GeradorExtraction(BaseModel):
    tipo_atendimento: str | None = None
    qtd: int | None = None
    potencia_kva: float | None = None
    circuitos_atendidos: str | None = None

class LLMExtraction(BaseModel):
    obra: ObraExtraction = ObraExtraction()
    energia: EnergiaExtraction = EnergiaExtraction()
    aterramento: AterramentoExtraction = AterramentoExtraction()
    mt: MTExtraction = MTExtraction()
    gerador: GeradorExtraction = GeradorExtraction()
    observacoes: str | None = None


# ── Prompt ────────────────────────────────────────────────────────────────────

PROMPT = """\
Você é um extrator estruturado de dados de projetos elétricos brasileiros.

Receberá texto extraído de pranchas técnicas de um projeto elétrico.
Extraia apenas os campos solicitados no schema.

Contexto técnico importante:
- MT = média tensão (tipicamente 13.8kV ou 15kV no Brasil). NÃO confunda com BT (baixa tensão: 220V/380V).
- mt.tensao_kv refere-se à tensão do RAMAL DE MÉDIA TENSÃO, não à tensão secundária.
- mt.secao_cabo_mm2 é a seção do cabo de MT, não de BT.
- energia.tem_subestacao = true se houver menção a subestação, transformador abaixador, ou medição em MT.
- energia.potencia_transformador_kva: potência nominal do transformador da subestação em kVA (ex: 500, 1000, 1500).
- energia.tap_descricao: descrição do tap do transformador (ex: "tap nominal", "tap +2,5%").
- energia.tensao_secundaria: tensão secundária do transformador (ex: "220/127V", "380/220V").
- aterramento.tipo_sistema: valores típicos são "TN-S", "TN-C-S", "TT", "IT".
- aterramento.local_bep: local do Barramento de Equipotencialização Principal (ex: "subsolo", "térreo").
- aterramento.secao_cabo_malha_mm2: seção do cabo da malha de aterramento, em mm².
- gerador.tipo_atendimento: deve ser um destes valores:
  "condominio" (atende áreas comuns), "edificio" (atende todo o edifício),
  "parcial" (atende apenas circuitos específicos como bombas/elevadores).
  Infira a partir do contexto do quadro de gerador.
- gerador.qtd: quantidade de grupos geradores.
- gerador.potencia_kva: potência nominal do gerador em kVA.
- gerador.circuitos_atendidos: quando tipo_atendimento="parcial", descreva quais circuitos o gerador atende (ex: "elevadores, bombas de recalque, iluminação de emergência").
- obra.tipo_edificacao: tipo geral (ex: "residencial", "comercial", "misto").
- obra.tipologia: descrição da tipologia (ex: "torre única", "2 torres", "condomínio horizontal").
- obra.qtd_lojas: quantidade de unidades comerciais/lojas, se houver.
- obra.qtd_restaurantes: quantidade de restaurantes, se houver.

Regras obrigatórias:
- Use apenas evidências presentes no texto fornecido.
- Se não houver evidência suficiente, retorne null.
- Não invente valores.
- Para valores numéricos, retorne número e não string.
- Em observacoes, resuma ambiguidades ou limitações da extração.
"""


def is_llm_extraction_enabled() -> bool:
    return bool(os.getenv("USE_LLM_EXTRACTION", "").strip())


def _get_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4.1")


def _get_client() -> Any:
    from openai import OpenAI
    return OpenAI()


def _build_input(texts: list[tuple[str, str]]) -> list[dict[str, Any]]:
    sections = [f"=== ARQUIVO: {name} ===\n{text}" for name, text in texts]
    return [{"role": "user", "content": f"{PROMPT}\n\n" + "\n\n".join(sections)}]


def _extract_batch(client: Any, model: str, texts: list[tuple[str, str]]) -> dict[str, Any]:
    response = client.responses.parse(
        model=model,
        input=_build_input(texts),
        text_format=LLMExtraction,
    )
    if response.output_parsed is None:
        return {}
    return response.output_parsed.model_dump(mode="json")


def _merge_partials(partials: list[dict[str, Any]]) -> dict[str, Any]:
    """First non-null value wins per field."""
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
    """Run hybrid extraction: text already extracted by PyMuPDF, GPT interprets."""
    if not is_llm_extraction_enabled():
        logger.debug("LLM extraction disabled, skipping")
        return {}

    file_texts = [
        (sf.original_filename, sf.extracted_text)
        for sf in source_files
        if sf.extracted_text.strip()
    ]
    if not file_texts:
        logger.info("No extractable text in source files, skipping LLM")
        return {}

    client = _get_client()
    model = _get_model()

    batches = [file_texts[i:i + BATCH_SIZE] for i in range(0, len(file_texts), BATCH_SIZE)]
    logger.info("LLM extraction: model=%s, files=%d, batches=%d", model, len(file_texts), len(batches))

    t0 = time.monotonic()
    partials: list[dict[str, Any]] = []

    for idx, batch in enumerate(batches):
        if idx > 0:
            time.sleep(RATE_LIMIT_WAIT_SECONDS)
        partials.append(_extract_batch(client, model, batch))

    merged = _merge_partials(partials)
    elapsed = time.monotonic() - t0
    field_count = sum(len(s) for s in merged.values() if isinstance(s, dict))
    logger.info("LLM extraction complete: fields=%d, elapsed=%.1fs", field_count, elapsed)

    return merged
