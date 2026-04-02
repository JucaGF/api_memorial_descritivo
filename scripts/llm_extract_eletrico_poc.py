from __future__ import annotations

"""
Extração híbrida: PyMuPDF extrai texto, GPT interpreta.

Uso:
  python scripts/llm_extract_eletrico_poc.py *.pdf --output resultado.json
  python scripts/llm_extract_eletrico_poc.py *.pdf --model gpt-4.1

Fluxo:
  1. PyMuPDF extrai texto de todos os PDFs
  2. GPT recebe o texto em lotes e extrai campos estruturados
  3. Resultados parciais são consolidados em um único JSON
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.llm_extractor import (  # noqa: E402
    PROMPT,
    LLMExtraction,
    _build_input,
    _merge_partials,
)

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
DEFAULT_BATCH_SIZE = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extração híbrida: PyMuPDF + GPT para memorial elétrico."
    )
    parser.add_argument("pdfs", nargs="+", help="Caminhos locais para PDFs.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Modelo OpenAI (default: {DEFAULT_MODEL}).")
    parser.add_argument("--output", type=Path, help="Caminho para salvar o JSON final.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"PDFs por lote (default: {DEFAULT_BATCH_SIZE}).")
    return parser.parse_args()


def validate_pdf_paths(paths: list[str]) -> list[Path]:
    validated: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF nao encontrado: {path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Arquivo nao e PDF: {path}")
        validated.append(path)
    return validated


def extract_text_from_pdf(pdf_path: Path) -> str:
    import fitz
    doc = fitz.open(str(pdf_path))
    pages: list[str] = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            pages.append(text)
    doc.close()
    return "\n\n".join(pages)


def extract_all_texts(pdf_paths: list[Path]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for pdf_path in pdf_paths:
        print(f"  Extraindo texto: {pdf_path.name}...", file=sys.stderr)
        text = extract_text_from_pdf(pdf_path)
        print(f"    -> {len(text)} caracteres", file=sys.stderr)
        results.append((pdf_path.name, text))
    return results


def run_batch_extraction(
    client: Any,
    model: str,
    file_texts: list[tuple[str, str]],
) -> dict[str, Any]:
    filenames = [ft[0] for ft in file_texts]
    print(f"  GPT processando: {', '.join(filenames)}...", file=sys.stderr)

    response = client.responses.parse(
        model=model,
        input=_build_input(file_texts),
        text_format=LLMExtraction,
    )
    if response.output_parsed is None:
        raise RuntimeError("A API retornou resposta sem output estruturado.")
    return response.output_parsed.model_dump(mode="json")


def merge_extractions(partials: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrapper that also collects observacoes from partials."""
    observations: list[str] = []
    for partial in partials:
        obs = partial.get("observacoes")
        if obs:
            observations.append(obs)

    merged = _merge_partials(partials)
    if observations:
        merged["observacoes"] = " | ".join(observations)
    return merged


def main() -> int:
    args = parse_args()

    try:
        pdf_paths = validate_pdf_paths(args.pdfs)

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY nao encontrado no ambiente.")

        print(f"\n[1/3] Extraindo texto de {len(pdf_paths)} PDFs com PyMuPDF...", file=sys.stderr)
        all_texts = extract_all_texts(pdf_paths)

        from openai import OpenAI
        client = OpenAI()

        batches = [
            all_texts[i:i + args.batch_size]
            for i in range(0, len(all_texts), args.batch_size)
        ]

        print(f"\n[2/3] Enviando {len(batches)} lotes ao GPT ({args.model})...", file=sys.stderr)
        partials: list[dict[str, Any]] = []
        for idx, batch in enumerate(batches, 1):
            if idx > 1:
                wait = 30
                print(f"\n  Aguardando {wait}s (rate limit)...", file=sys.stderr)
                time.sleep(wait)
            print(f"\n  Lote {idx}/{len(batches)}:", file=sys.stderr)
            partials.append(run_batch_extraction(client, args.model, batch))

        print(f"\n[3/3] Merge de {len(partials)} resultados parciais...", file=sys.stderr)
        final = merge_extractions(partials)

        rendered = json.dumps(final, ensure_ascii=False, indent=2)
        print(rendered)

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(f"\nSalvo em: {args.output}", file=sys.stderr)

        return 0
    except Exception as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
