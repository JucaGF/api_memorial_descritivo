from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.services.memorial_renderer import (
    MemorialRenderError,
    assert_no_internal_markers_left,
    assert_no_jinja_left,
    has_docx_render_dependencies,
    inspect_docx_text,
    render_memorial_eletrico_v1,
)
from app.services.memorial_validator import validate_memorial_eletrico_v1_context


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "eletrico_sem_subestacao.json"


def load_fixture() -> dict:
    with FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_valid_context() -> dict:
    context = load_fixture()
    item_keys = [
        "cpct",
        "cftv",
        "alarme_patrimonial",
        "sonorizacao",
        "alarme_incendio",
        "automacao",
    ]
    context["nao_inclusos"]["tem_itens"] = any(
        bool(context["nao_inclusos"].get(key, False)) for key in item_keys
    )
    validate_memorial_eletrico_v1_context(context)
    return context


class MemorialRendererTests(unittest.TestCase):
    @unittest.skipUnless(
        has_docx_render_dependencies(),
        "python-docx e docxtpl nao estao instalados no ambiente",
    )
    def test_render_memorial_eletrico_v1_generates_docx_without_template_tokens(self) -> None:
        tmp_dir = ROOT / "tests" / "output"
        output_path = tmp_dir / "renderer_test_output.docx"

        render_memorial_eletrico_v1(build_valid_context(), output_path)

        self.assertTrue(output_path.exists())
        text = inspect_docx_text(output_path)
        self.assertNotIn("{{", text)
        self.assertNotIn("{%", text)

    def test_assert_no_jinja_left_raises_structured_error(self) -> None:
        with self.assertRaises(MemorialRenderError) as error_info:
            assert_no_jinja_left("trecho com {{ placeholder }}")

        self.assertIn("Jinja", str(error_info.exception))

    def test_assert_no_internal_markers_left_raises_structured_error(self) -> None:
        with self.assertRaises(MemorialRenderError) as error_info:
            assert_no_internal_markers_left("Texto Fixo do template")

        self.assertIn("template", str(error_info.exception))


if __name__ == "__main__":
    unittest.main()
