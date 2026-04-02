from __future__ import annotations

"""
Vision-first extraction: page images + OCR text sent to GPT for structured extraction.

Usage:
  python scripts/llm_extract_eletrico_poc.py projects/eletrico/*.pdf
  python scripts/llm_extract_eletrico_poc.py projects/eletrico/*.pdf --output tests/output/vision_extract.json
  python scripts/llm_extract_eletrico_poc.py projects/eletrico/*.pdf --model gpt-5.4

Pipeline:
  1. PyMuPDF extracts text + renders page images from each PDF
  2. GPT receives images + text per file and returns structured extraction
  3. When multiple files, a second GPT pass merges per-file results
  4. Mapper supplements any remaining gaps
  5. Coverage report shows filled/missing/pending fields
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
os.environ["USE_LLM_EXTRACTION"] = "true"
sys.path.insert(0, str(ROOT))

from app.services.file_ingestion import IngestedFileMetadata  # noqa: E402
from app.services.pipeline_from_files import extract_mapping_from_ingested_files  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vision-first extraction for memorial eletrico.",
    )
    parser.add_argument("pdfs", nargs="+", help="PDF file paths.")
    parser.add_argument("--model", help="Override OPENAI_MODEL env var.")
    parser.add_argument("--output", type=Path, help="Save extraction JSON to this path.")
    parser.add_argument("--report", action="store_true", help="Print coverage report.")
    return parser.parse_args()


def validate_and_build_files(paths: list[str]) -> list[IngestedFileMetadata]:
    files: list[IngestedFileMetadata] = []
    for raw_path in paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        if path.suffix.lower() != ".pdf":
            raise ValueError(f"Not a PDF: {path}")
        files.append(IngestedFileMetadata(
            original_filename=path.name,
            stored_filename=path.name,
            content_type="application/pdf",
            extension=".pdf",
            size_bytes=path.stat().st_size,
            saved_path=str(path),
        ))
    return files


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if args.model:
        os.environ["OPENAI_MODEL"] = args.model

    try:
        files = validate_and_build_files(args.pdfs)
        print(f"\nExtracting from {len(files)} PDFs...", file=sys.stderr)

        mapping, report = extract_mapping_from_ingested_files(files)

        rendered = json.dumps(mapping.context, ensure_ascii=False, indent=2)
        print(rendered)

        if args.report:
            print(f"\n--- Coverage Report ---", file=sys.stderr)
            print(f"Filled ({len(report.filled)}): {report.filled}", file=sys.stderr)
            print(f"Missing ({len(report.missing)}): {report.missing}", file=sys.stderr)
            print(f"Pending ({len(report.pending)}): {report.pending}", file=sys.stderr)

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            output_data = {
                "context": mapping.context,
                "report": asdict(report),
            }
            args.output.write_text(
                json.dumps(output_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"\nSaved to: {args.output}", file=sys.stderr)

        return 0
    except Exception as error:
        logging.exception("Extraction failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
