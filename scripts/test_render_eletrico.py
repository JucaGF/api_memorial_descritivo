from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.context_builder import build_memorial_eletrico_v1_context
from app.services.memorial_renderer import (
    inspect_docx_text,
    render_memorial_eletrico_v1,
)
from app.services.memorial_validator import validate_memorial_eletrico_v1_context


FIXTURES_DIR = ROOT / "tests" / "fixtures"
OUTPUT_DIR = ROOT / "tests" / "output"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def assert_file_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} não encontrado em: {path}")


def assert_contains(text: str, expected: str, label: str) -> None:
    if expected not in text:
        raise AssertionError(f"[{label}] Texto esperado não encontrado: {expected!r}")


def assert_not_contains(text: str, unexpected: str, label: str) -> None:
    if unexpected in text:
        raise AssertionError(f"[{label}] Texto não deveria aparecer: {unexpected!r}")


def render_template(payload_path: Path) -> tuple[Path, dict[str, Any]]:
    payload = build_memorial_eletrico_v1_context(load_json(payload_path))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    normalized_payload_path = OUTPUT_DIR / f"{payload_path.stem}_normalizado.json"
    save_json(normalized_payload_path, payload)

    output_path = OUTPUT_DIR / f"{payload_path.stem}_renderizado.docx"
    validate_memorial_eletrico_v1_context(payload)
    render_memorial_eletrico_v1(payload, output_path)

    return output_path, payload


def debug_lines_with_fragment(text: str, fragment: str) -> None:
    if fragment in text:
        print(f"\n[DEBUG] Linhas com {fragment!r}:")
        for line in text.splitlines():
            if fragment in line:
                print(repr(line))


def run_case(filename: str) -> None:
    payload_path = FIXTURES_DIR / filename
    assert_file_exists(payload_path, "Payload de teste")

    output_path, payload = render_template(payload_path)
    text = inspect_docx_text(output_path)

    energia = payload["energia"]
    gerador = payload["gerador"]
    nao_inclusos = payload["nao_inclusos"]

    assert_contains(text, payload["obra"]["nome"], filename)
    assert_contains(text, payload["obra"]["construtora"], filename)
    assert_contains(text, payload["documento"]["data_atual"], filename)

    if energia["tem_subestacao"]:
        if payload["energia"]["tipo_subestacao"]:
            assert_contains(text, payload["energia"]["tipo_subestacao"], filename)
        if payload["energia"]["potencia_transformador_kva"] is not None:
            assert_contains(text, str(payload["energia"]["potencia_transformador_kva"]), filename)
    else:
        assert_not_contains(text, "DETALHES DA SUBESTAÇÃO", filename)

    if gerador["tipo_atendimento"] == "parcial":
        assert_contains(text, gerador["circuitos_atendidos"], filename)

    itens_marcados = {
        "CPCT": nao_inclusos["cpct"],
        "CFTV": nao_inclusos["cftv"],
        "Alarme para segurança patrimonial": nao_inclusos["alarme_patrimonial"],
        "Sistema de sonorização": nao_inclusos["sonorizacao"],
        "Sistema de detecção e alarme de incêndio": nao_inclusos["alarme_incendio"],
        "Sistema de automação e supervisão": nao_inclusos["automacao"],
    }

    texto_introdutorio_itens_nao_inclusos = (
        "Os seguintes equipamentos e aparelhos serão de fornecimento da construtora"
    )

    debug_lines_with_fragment(text, "ITENS NÃO INCLUSOS")

    if nao_inclusos["tem_itens"]:
        assert_contains(text, texto_introdutorio_itens_nao_inclusos, filename)
        for item_text, is_selected in itens_marcados.items():
            if is_selected:
                assert_contains(text, item_text, filename)
            else:
                assert_not_contains(text, item_text, filename)
    else:
        assert_not_contains(text, texto_introdutorio_itens_nao_inclusos, filename)
        for item_text in itens_marcados:
            assert_not_contains(text, item_text, filename)

    print(f"[OK] {filename} -> {output_path}")


def main() -> None:
    cases = [
        "eletrico_com_subestacao.json",
        "eletrico_sem_subestacao.json",
    ]

    for case in cases:
        run_case(case)

    print("\nTodos os testes básicos de renderização passaram.")


if __name__ == "__main__":
    main()
