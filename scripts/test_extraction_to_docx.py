from __future__ import annotations

"""
End-to-end test: PDF extraction -> context build -> validation -> DOCX render.

Extracts data from real PDFs using the vision pipeline, fills any remaining
required fields with placeholder values, then renders the memorial DOCX.

Usage:
  python scripts/test_extraction_to_docx.py
  python scripts/test_extraction_to_docx.py --pdfs projects/eletrico/MGAMAK_EL_E-1.0_SUBSOLO_V08.pdf
  python scripts/test_extraction_to_docx.py --output tests/output/makai_from_extraction.docx
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
os.environ["USE_LLM_EXTRACTION"] = "true"
sys.path.insert(0, str(ROOT))

from app.services.file_ingestion import IngestedFileMetadata  # noqa: E402
from app.services.memorial_renderer import inspect_docx_text  # noqa: E402
from app.services.memorial_validator import MemorialValidationError  # noqa: E402
from app.services.pipeline import generate_memorial_eletrico_v1  # noqa: E402
from app.services.pipeline_from_files import extract_mapping_from_ingested_files  # noqa: E402

DEFAULT_PDFS = [
    "projects/eletrico/MGAMAK_EL_E-1.0_SUBSOLO_V08.pdf",
    "projects/eletrico/MGAMAK_EL_E-1.1_QUADROS E DIAGRAMAS_V08.pdf",
    "projects/eletrico/MGAMAK_EL_E-6.0_ENERGISA_V01.pdf",
]
DEFAULT_OUTPUT = "tests/output/makai_from_extraction.docx"

REQUIRED_PLACEHOLDERS = {
    "obra.numero_cadastro": "N/A",
    "obra.construtora": "N/A",
    "obra.nome": "N/A",
    "obra.localizacao": "N/A",
    "obra.tipo_edificacao": "residencial",
    "obra.tipologia": "torre única",
    "obra.qtd_apartamentos": 0,
    "obra.qtd_lojas": 0,
    "obra.qtd_restaurantes": 0,
    "energia.tem_subestacao": False,
    "aterramento.tipo_sistema": "TT",
    "aterramento.qtd_hastes": 1,
    "aterramento.secao_cabo_cobre_mm2": 50,
    "aterramento.secao_cabo_malha_mm2": 50,
    "aterramento.local_bep": "subsolo",
    "gerador.tipo_atendimento": "condominio",
    "gerador.qtd": 1,
    "gerador.potencia_kva": 150,
    "instalacao.perfilado_tipo": "eletrocalha",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract from PDFs and render memorial DOCX.")
    parser.add_argument("--pdfs", nargs="+", default=DEFAULT_PDFS, help="PDF file paths.")
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT), help="Output DOCX path.")
    parser.add_argument("--context-out", type=Path, help="Save final context JSON to this path.")
    return parser.parse_args()


def build_ingested_files(pdf_paths: list[str]) -> list[IngestedFileMetadata]:
    files = []
    for raw_path in pdf_paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        files.append(IngestedFileMetadata(
            original_filename=path.name,
            stored_filename=path.name,
            content_type="application/pdf",
            extension=".pdf",
            size_bytes=path.stat().st_size,
            saved_path=str(path),
        ))
    return files


def fill_required_placeholders(context: dict) -> list[str]:
    """Fill required fields that are still null with placeholder values. Returns list of filled paths."""
    filled = []
    for dotted_path, placeholder in REQUIRED_PLACEHOLDERS.items():
        section_key, field_key = dotted_path.split(".")
        section = context.get(section_key, {})
        if not isinstance(section, dict):
            section = {}
            context[section_key] = section
        if section.get(field_key) is None:
            section[field_key] = placeholder
            filled.append(f"{dotted_path}={placeholder}")
    return filled


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    log = logging.getLogger("test_e2e")

    try:
        files = build_ingested_files(args.pdfs)
        log.info("Step 1/4: Extracting from %d PDFs...", len(files))
        mapping, report = extract_mapping_from_ingested_files(files)

        log.info("Filled: %d, Missing: %d, Pending: %d",
                 len(report.filled), len(report.missing), len(report.pending))

        log.info("Step 2/4: Filling required placeholders...")
        filled_placeholders = fill_required_placeholders(mapping.context)
        if filled_placeholders:
            log.warning("Placeholders used (human review needed): %s", filled_placeholders)
        else:
            log.info("No placeholders needed -- all required fields were extracted.")

        log.info("Step 3/4: Validating and rendering DOCX...")
        result = generate_memorial_eletrico_v1(mapping.context, args.output)

        log.info("Step 4/4: Verifying output...")
        text = inspect_docx_text(result.output_path)
        context = result.context

        checks_passed = 0
        checks_failed = 0

        def check(label: str, condition: bool) -> None:
            nonlocal checks_passed, checks_failed
            if condition:
                checks_passed += 1
            else:
                checks_failed += 1
                log.error("FAIL: %s", label)

        check("obra.nome in doc", context["obra"]["nome"] in text)
        check("obra.construtora in doc", context["obra"]["construtora"] in text)
        check("documento.data_atual in doc", context["documento"]["data_atual"] in text)
        check("aterramento.tipo_sistema in doc", context["aterramento"]["tipo_sistema"] in text)
        check("instalacao.perfilado_tipo in doc", context["instalacao"]["perfilado_tipo"] in text)

        if not context["energia"]["tem_subestacao"]:
            check("no subestacao section", "DETALHES DA SUBESTAÇÃO" not in text)

        check("no jinja tokens", "{{" not in text and "{%" not in text)

        log.info("Checks: %d passed, %d failed", checks_passed, checks_failed)
        log.info("DOCX rendered: %s", result.output_path)

        if args.context_out:
            args.context_out.parent.mkdir(parents=True, exist_ok=True)
            args.context_out.write_text(
                json.dumps(context, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            log.info("Context saved: %s", args.context_out)

        return 1 if checks_failed else 0

    except MemorialValidationError as error:
        log.error("Validation failed: %s", error)
        log.error("Issues: %s", [f"{i.path}: {i.message}" for i in error.issues])
        return 1
    except Exception:
        logging.exception("Pipeline failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
