"""
Acceptance: real from-files pipeline (eletrico-canteiro v1) on the Bothanic drawings,
compared with tests/fixtures/eletrico_canteiro_bothanic_expected.json.

Run with the LLM on (needs OPENAI_API_KEY; model from OPENAI_MODEL):
  APP_ENV=local USE_LLM_EXTRACTION=true python scripts/acceptance_canteiro_bothanic.py

Exit code: 0 = no divergence; 1 = divergences; 2 = validation error / failure.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from starlette.datastructures import Headers, UploadFile  # noqa: E402

from app.services.memorial_validator import MemorialValidationError  # noqa: E402
from app.services.pipeline_from_files import (  # noqa: E402
    generate_memorial_eletrico_canteiro_v1_from_uploaded_files,
)

DEFAULT_PDFS = [
    "projects/canteiro/01_CANTEIRO OBRA BOTHANIC_V05.pdf",
    "projects/canteiro/02_CANTEIRO OBRA BOTHANIC_V05.pdf",
]
EXPECTED_PATH = ROOT / "tests" / "fixtures" / "eletrico_canteiro_bothanic_expected.json"


def _get(data: Any, dotted: str) -> Any:
    current = data
    for part in dotted.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def compare(expected: dict[str, Any], context: dict[str, Any]) -> list[str]:
    divergences: list[str] = []

    for path in (
        "obra.construtora",
        "energia.potencia_transformador_kva",
        "aterramento.qtd_hastes",
    ):
        want, got = _get(expected, path), _get(context, path)
        if want != got:
            divergences.append(f"{path}: esperado {want!r}, obtido {got!r}")

    if _get(context, "mt.tensao_kv") != 13.8:
        divergences.append(
            f"mt.tensao_kv: esperado 13.8, obtido {_get(context, 'mt.tensao_kv')!r}"
        )
    for path in ("mt.secao_cabo_mm2", "mt.diametro_eletroduto_pol"):
        if _get(context, path) is not None:
            divergences.append(f"{path}: esperado None, obtido {_get(context, path)!r}")

    got_quadros = {
        _norm(q.get("nome")): q.get("carga_w")
        for q in (context.get("quadros") or [])
        if isinstance(q, dict)
    }
    for quadro in expected.get("quadros", []):
        key = _norm(quadro["nome"])
        if key not in got_quadros:
            divergences.append(f"quadros: '{quadro['nome']}' ausente")
        elif got_quadros[key] != quadro["carga_w"]:
            divergences.append(
                f"quadros['{quadro['nome']}'].carga_w: esperado {quadro['carga_w']!r}, "
                f"obtido {got_quadros[key]!r}"
            )

    got_equip = {
        _norm(e.get("nome"))
        for e in (context.get("equipamentos") or [])
        if isinstance(e, dict)
    }
    for equip in expected.get("equipamentos", []):
        if _norm(equip["nome"]) not in got_equip:
            divergences.append(f"equipamentos: '{equip['nome']}' ausente")

    return divergences


def _print_report(report: Any) -> None:
    if report is None:
        print("extraction_report: (nenhum)")
        return
    data = asdict(report) if is_dataclass(report) else dict(report)
    print("extraction_report:")
    print(f"  filled ({len(data.get('filled', []))}): {data.get('filled')}")
    print(f"  missing ({len(data.get('missing', []))}): {data.get('missing')}")
    print(f"  pending ({len(data.get('pending', []))}): {data.get('pending')}")
    cross = data.get("cross_validation") or {}
    adjustments = cross.get("canteiro_list_adjustments")
    print(f"  canteiro_list_adjustments: {json.dumps(adjustments, ensure_ascii=False, indent=2) if adjustments else 'nenhum'}")


def _build_uploads(pdfs: list[Path]) -> list[UploadFile]:
    return [
        UploadFile(
            filename=pdf.name,
            file=io.BytesIO(pdf.read_bytes()),
            headers=Headers({"content-type": "application/pdf"}),
        )
        for pdf in pdfs
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pdfs", nargs="+", default=DEFAULT_PDFS)
    parser.add_argument("--output", default=None, help="DOCX de saida (default: tmp dir)")
    args = parser.parse_args()

    pdfs = [(ROOT / p) if not Path(p).is_absolute() else Path(p) for p in args.pdfs]
    missing = [str(p) for p in pdfs if not p.is_file()]
    if missing:
        print(f"PDFs nao encontrados: {missing}", file=sys.stderr)
        return 2

    output = Path(args.output) if args.output else Path(tempfile.mkdtemp(prefix="canteiro_acceptance_")) / "memorial_eletrico_canteiro_v1.docx"
    output.parent.mkdir(parents=True, exist_ok=True)
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))

    try:
        result = asyncio.run(
            generate_memorial_eletrico_canteiro_v1_from_uploaded_files(
                _build_uploads(pdfs), output
            )
        )
    except MemorialValidationError as error:
        print("FALHA: MemorialValidationError")
        for issue in error.issues:
            print(f"  - {issue.path}: {issue.message}")
        _print_report(error.extraction_report)
        return 2

    print(f"DOCX gerado: {result.output_path}")
    _print_report(result.extraction_report)

    divergences = compare(expected, result.context)
    if divergences:
        print(f"\n{len(divergences)} divergencia(s):")
        for d in divergences:
            print(f"  - {d}")
        return 1
    print("\nOK: zero divergencias.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
