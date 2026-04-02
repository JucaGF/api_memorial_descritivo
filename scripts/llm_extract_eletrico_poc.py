from __future__ import annotations

"""
Uso rapido:

  OPENAI_API_KEY=... .venv/bin/python scripts/llm_extract_eletrico_poc.py \
    /caminho/arquivo1.pdf /caminho/arquivo2.pdf \
    --output tests/output/llm_extract_result.json

Modelo:

  - usa OPENAI_MODEL se definido
  - default conservador: gpt-4o-mini
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel


DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


class ObraExtraction(BaseModel):
    construtora: str | None = None
    nome: str | None = None
    localizacao: str | None = None
    numero_cadastro: str | None = None


class EnergiaExtraction(BaseModel):
    tem_subestacao: bool | None = None
    tipo_subestacao: str | None = None


class AterramentoExtraction(BaseModel):
    tipo_sistema: str | None = None


class MTExtraction(BaseModel):
    tensao_kv: float | None = None
    secao_cabo_mm2: float | None = None


class GeradorExtraction(BaseModel):
    tipo_atendimento: str | None = None


class MemorialEletricoLLMExtraction(BaseModel):
    obra: ObraExtraction
    energia: EnergiaExtraction
    aterramento: AterramentoExtraction
    mt: MTExtraction
    gerador: GeradorExtraction
    observacoes: str | None = None


PROMPT = """\
Você é um extrator estruturado de dados de projetos elétricos brasileiros.

Receberá um ou mais PDFs de pranchas e documentos técnicos de um projeto
elétrico. Extraia apenas os campos solicitados no schema.

Regras obrigatórias:
- Use apenas evidências presentes nos PDFs fornecidos.
- Se não houver evidência suficiente, retorne null.
- Não invente valores.
- Considere carimbos, folhas da concessionária, diagramas, quadros e notas.
- Para energia.tem_subestacao, retorne true ou false apenas se houver evidência
  razoável; caso contrário, retorne null.
- Para valores numéricos como mt.tensao_kv e mt.secao_cabo_mm2, retorne número
  e não string.
- Em observacoes, resuma em poucas linhas ambiguidades ou limitações relevantes
  da extração.
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "PoC de extração estruturada do memorial elétrico via OpenAI "
            "Responses API com PDFs."
        )
    )
    parser.add_argument(
        "pdfs",
        nargs="+",
        help="Um ou mais caminhos locais para arquivos PDF.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "Modelo OpenAI a usar. Default: OPENAI_MODEL se definido, "
            f"senao {DEFAULT_MODEL}."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Caminho opcional para salvar o JSON extraído.",
    )
    parser.add_argument(
        "--keep-remote-files",
        action="store_true",
        help="Nao apagar os arquivos enviados para a OpenAI ao final da execucao.",
    )
    return parser.parse_args()


def validate_pdf_paths(paths: list[str]) -> list[Path]:
    validated: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF nao encontrado: {path}")
        if not path.is_file():
            raise ValueError(f"Caminho informado nao e arquivo: {path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Arquivo nao e PDF: {path}")
        validated.append(path)
    return validated


def require_openai_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY nao encontrado no ambiente. "
            "Defina a variavel antes de executar o script."
        )
    return api_key


def upload_pdf_files(client: Any, pdf_paths: list[Path]) -> list[str]:
    uploaded_ids: list[str] = []
    for pdf_path in pdf_paths:
        with pdf_path.open("rb") as file_handle:
            uploaded = client.files.create(file=file_handle, purpose="user_data")
        uploaded_ids.append(uploaded.id)
    return uploaded_ids


def build_response_input(file_ids: list[str]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {"type": "input_file", "file_id": file_id} for file_id in file_ids
    ]
    content.append({"type": "input_text", "text": PROMPT})
    return [{"role": "user", "content": content}]


def run_extraction(
    model: str,
    pdf_paths: list[Path],
    keep_remote_files: bool = False,
) -> MemorialEletricoLLMExtraction:
    from openai import OpenAI

    require_openai_api_key()
    client = OpenAI()
    file_ids: list[str] = []

    try:
        file_ids = upload_pdf_files(client, pdf_paths)
        response = client.responses.parse(
            model=model,
            input=build_response_input(file_ids),
            text_format=MemorialEletricoLLMExtraction,
        )
        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("A API retornou resposta sem output estruturado parseado.")
        return parsed
    finally:
        if not keep_remote_files:
            for file_id in file_ids:
                try:
                    client.files.delete(file_id)
                except Exception:
                    continue


def write_output(result: MemorialEletricoLLMExtraction, output_path: Path | None) -> None:
    payload = result.model_dump(mode="json")
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    print(rendered)

    if output_path is None:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    try:
        pdf_paths = validate_pdf_paths(args.pdfs)
        result = run_extraction(args.model, pdf_paths, keep_remote_files=args.keep_remote_files)
        write_output(result, args.output)
        return 0
    except Exception as error:
        print(f"Erro ao executar a PoC de extração LLM: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
