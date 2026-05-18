from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.diameter_normalizer import normalize_diameter


ROOT_DIR = Path(__file__).resolve().parents[2]
ELETRICO_V1_TEMPLATE_PATH = ROOT_DIR / "templates" / "eletrico" / "v1" / "template.docx"
TELECOM_V1_TEMPLATE_PATH = ROOT_DIR / "templates" / "telecom" / "v1" / "template.docx"
GAS_NATURAL_V1_TEMPLATE_PATH = ROOT_DIR / "templates" / "gas_natural" / "v1" / "template.docx"
GLP_V1_TEMPLATE_PATH = ROOT_DIR / "templates" / "glp" / "v1" / "template.docx"
GLP_V2_TEMPLATE_PATH = ROOT_DIR / "templates" / "glp" / "v2" / "template.docx"
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


def _diameter_payload(raw_value: str | None, *, inferido: bool = False) -> dict[str, Any]:
    normalized = normalize_diameter(raw_value)
    if normalized is None:
        return {
            "valor": 0,
            "unidade": "mm",
            "valor_formatado": raw_value or "",
            "valor_original": raw_value or "",
            "inferido": inferido,
        }
    return {
        "valor": float(normalized.valor),
        "unidade": normalized.unidade,
        "valor_formatado": normalized.valor_formatado,
        "valor_original": normalized.valor_original,
        "inferido": inferido,
    }


def _with_glp_v2_template_aliases(context: dict[str, Any]) -> dict[str, Any]:
    """Allow legacy GLP v1 pipelines to render a DOCX already migrated to v2 paths."""
    render_context = deepcopy(context)

    obra = render_context.get("obra")
    if isinstance(obra, dict) and isinstance(obra.get("qtd_apartamentos"), int):
        obra["qtd_apartamentos"] = {"valor": obra["qtd_apartamentos"]}

    abastecimento = render_context.get("abastecimento")
    if isinstance(abastecimento, dict):
        render_context.setdefault(
            "tanques",
            {
                "quantidade": abastecimento.get("qtd_tanques", 0),
                "tipo": "P-190",
                "qtd_abrigos": abastecimento.get("qtd_tanques", 0),
            },
        )

    dimensionamento = render_context.get("dimensionamento")
    soma = render_context.get("soma")
    if isinstance(dimensionamento, dict):
        fogao = int(dimensionamento.get("qtd_fogao") or 0)
        aquecedor = int(dimensionamento.get("qtd_aquecedor") or 0)
        churrasqueira = int(dimensionamento.get("qtd_churrasqueira") or 0)
        total = (
            soma.get("qtd_pontos_de_utilizacao")
            if isinstance(soma, dict)
            else None
        )
        render_context.setdefault(
            "pontos_utilizacao",
            {
                "fogao": fogao,
                "aquecedor": aquecedor,
                "churrasqueira": churrasqueira,
                "outros": 0,
                "total_calculado": int(total if total is not None else fogao + aquecedor + churrasqueira),
            },
        )

    ramal = render_context.get("ramal")
    if isinstance(ramal, dict):
        raw_diameter = ramal.get("primario_diametro")
        render_context.setdefault(
            "diametros",
            {
                "tubulacao_principal": _diameter_payload(raw_diameter),
                "valvula_esfera": _diameter_payload(raw_diameter, inferido=True),
            },
        )

    return render_context


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


def render_memorial_telecom_v1(
    context: dict[str, Any],
    output_path: Path,
) -> Path:
    _require_docx_dependencies()
    from docxtpl import DocxTemplate

    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = DocxTemplate(str(TELECOM_V1_TEMPLATE_PATH))
    document.render(context)
    document.save(str(output_path))

    rendered_text = inspect_docx_text(output_path)
    assert_no_jinja_left(rendered_text)
    assert_no_internal_markers_left(rendered_text)
    return output_path


def render_memorial_gas_natural_v1(
    context: dict[str, Any],
    output_path: Path,
) -> Path:
    _require_docx_dependencies()
    from docxtpl import DocxTemplate

    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = DocxTemplate(str(GAS_NATURAL_V1_TEMPLATE_PATH))
    document.render(context)
    document.save(str(output_path))

    rendered_text = inspect_docx_text(output_path)
    assert_no_jinja_left(rendered_text)
    assert_no_internal_markers_left(rendered_text)
    return output_path


def render_memorial_glp_v1(
    context: dict[str, Any],
    output_path: Path,
) -> Path:
    _require_docx_dependencies()
    from docxtpl import DocxTemplate

    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = DocxTemplate(str(GLP_V1_TEMPLATE_PATH))
    document.render(_with_glp_v2_template_aliases(context))
    document.save(str(output_path))

    rendered_text = inspect_docx_text(output_path)
    assert_no_jinja_left(rendered_text)
    assert_no_internal_markers_left(rendered_text)
    return output_path


def render_memorial_glp_v2(
    context: dict[str, Any],
    output_path: Path,
) -> Path:
    _require_docx_dependencies()
    from docxtpl import DocxTemplate

    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = DocxTemplate(str(GLP_V2_TEMPLATE_PATH))
    document.render(context)
    document.save(str(output_path))

    rendered_text = inspect_docx_text(output_path)
    assert_no_jinja_left(rendered_text)
    assert_no_internal_markers_left(rendered_text)
    return output_path
