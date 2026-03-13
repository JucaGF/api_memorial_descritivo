from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from docx import Document
from docxtpl import DocxTemplate
from jsonschema import validate


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT / "templates" / "eletrico" / "v1" / "template.docx"
SCHEMA_PATH = ROOT / "templates" / "eletrico" / "v1" / "schema.json"
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


def recompute_tem_itens(payload: dict[str, Any]) -> None:
    nao_inclusos = payload.get("nao_inclusos", {})
    item_keys = [
        "cpct",
        "cftv",
        "alarme_patrimonial",
        "sonorizacao",
        "alarme_incendio",
        "automacao",
    ]
    nao_inclusos["tem_itens"] = any(bool(nao_inclusos.get(key, False)) for key in item_keys)
    payload["nao_inclusos"] = nao_inclusos


def inspect_docx_text(docx_path: Path) -> str:
    document = Document(str(docx_path))
    paragraphs = [p.text for p in document.paragraphs]
    return "\n".join(paragraphs)


def assert_no_jinja_left(text: str) -> None:
    forbidden_tokens = ["{{", "}}", "{%", "%}"]
    found = [token for token in forbidden_tokens if token in text]
    if found:
        raise AssertionError(f"O DOCX renderizado ainda contém tokens Jinja: {found}")


def assert_no_internal_markers_left(text: str) -> None:
    forbidden_fragments = [
        "Fixo",
        "FIXO",
        "Podem ser incluídas caixas",
        "colocar as opções em caixas",
    ]
    found = [frag for frag in forbidden_fragments if frag in text]
    if found:
        raise AssertionError(f"O DOCX renderizado ainda contém texto interno de template: {found}")


def assert_contains(text: str, expected: str, label: str) -> None:
    if expected not in text:
        raise AssertionError(f"[{label}] Texto esperado não encontrado: {expected!r}")


def assert_not_contains(text: str, unexpected: str, label: str) -> None:
    if unexpected in text:
        raise AssertionError(f"[{label}] Texto não deveria aparecer: {unexpected!r}")


def render_template(payload_path: Path) -> tuple[Path, dict[str, Any]]:
    schema = load_json(SCHEMA_PATH)
    payload = load_json(payload_path)

    recompute_tem_itens(payload)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    normalized_payload_path = OUTPUT_DIR / f"{payload_path.stem}_normalizado.json"
    save_json(normalized_payload_path, payload)

    validate(instance=payload, schema=schema)

    doc = DocxTemplate(str(TEMPLATE_PATH))
    doc.render(payload)

    output_path = OUTPUT_DIR / f"{payload_path.stem}_renderizado.docx"
    doc.save(str(output_path))

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

    assert_no_jinja_left(text)
    assert_no_internal_markers_left(text)

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
    assert_file_exists(TEMPLATE_PATH, "Template DOCX")
    assert_file_exists(SCHEMA_PATH, "Schema JSON")

    cases = [
        "eletrico_com_subestacao.json",
        "eletrico_sem_subestacao.json",
    ]

    for case in cases:
        run_case(case)

    print("\nTodos os testes básicos de renderização passaram.")


if __name__ == "__main__":
    main()