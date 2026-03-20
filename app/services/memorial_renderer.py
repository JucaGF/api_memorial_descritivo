from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
ELETRICO_V1_TEMPLATE_PATH = ROOT_DIR / "templates" / "eletrico" / "v1" / "template.docx"
FORBIDDEN_JINJA_TOKENS = ("{{", "}}", "{%", "%}")
FORBIDDEN_INTERNAL_MARKERS = (
    "Fixo",
    "FIXO",
    "Podem ser incluídas caixas",
    "colocar as opções em caixas",
)


class MemorialRenderError(Exception):
    pass


def has_docx_render_dependencies() -> bool:
    return importlib.util.find_spec("docx") is not None and importlib.util.find_spec("docxtpl") is not None


def _require_docx_dependencies() -> None:
    if has_docx_render_dependencies():
        return
    raise MemorialRenderError(
        "Dependencias de renderizacao ausentes: instale python-docx e docxtpl."
    )


def inspect_docx_text(docx_path: Path) -> str:
    _require_docx_dependencies()
    from docx import Document

    document = Document(str(docx_path))
    paragraphs = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(paragraphs)


def assert_no_jinja_left(text: str) -> None:
    found = [token for token in FORBIDDEN_JINJA_TOKENS if token in text]
    if found:
        raise MemorialRenderError(
            f"O DOCX renderizado ainda contem tokens Jinja: {found}"
        )


def assert_no_internal_markers_left(text: str) -> None:
    found = [fragment for fragment in FORBIDDEN_INTERNAL_MARKERS if fragment in text]
    if found:
        raise MemorialRenderError(
            f"O DOCX renderizado ainda contem texto interno de template: {found}"
        )


def render_memorial_eletrico_v1(
    context: dict[str, Any],
    output_path: Path,
) -> Path:
    _require_docx_dependencies()
    from docxtpl import DocxTemplate

    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = DocxTemplate(str(ELETRICO_V1_TEMPLATE_PATH))
    document.render(context)
    document.save(str(output_path))

    rendered_text = inspect_docx_text(output_path)
    assert_no_jinja_left(rendered_text)
    assert_no_internal_markers_left(rendered_text)
    return output_path
