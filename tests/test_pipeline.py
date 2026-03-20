from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from app.services.memorial_validator import MemorialValidationError, ValidationIssue
from app.services.pipeline import PipelineResult, generate_memorial_eletrico_v1


ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures"


def load_fixture(filename: str) -> dict:
    with (FIXTURES_DIR / filename).open("r", encoding="utf-8") as file:
        return json.load(file)


class PipelineTests(unittest.TestCase):
    @patch("app.services.pipeline.validate_memorial_eletrico_v1_context")
    @patch("app.services.pipeline.render_memorial_eletrico_v1")
    def test_generate_memorial_eletrico_v1_builds_valid_context_and_renders(
        self,
        render_mock,
        validate_mock,
    ) -> None:
        payload = load_fixture("eletrico_com_subestacao.json")
        payload["nao_inclusos"]["tem_itens"] = False
        output_path = ROOT / "tests" / "output" / "pipeline_renderizado.docx"
        render_mock.return_value = output_path
        validate_mock.return_value = []

        result = generate_memorial_eletrico_v1(payload, output_path)

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.output_path, output_path)
        self.assertTrue(result.context["nao_inclusos"]["tem_itens"])
        self.assertIsNone(result.context["gerador"]["circuitos_atendidos"])
        validate_mock.assert_called_once_with(result.context)
        render_mock.assert_called_once_with(result.context, output_path)

    @patch("app.services.pipeline.validate_memorial_eletrico_v1_context")
    @patch("app.services.pipeline.render_memorial_eletrico_v1")
    def test_generate_memorial_eletrico_v1_does_not_render_when_validation_fails(
        self,
        render_mock,
        validate_mock,
    ) -> None:
        payload = load_fixture("eletrico_sem_subestacao.json")
        del payload["obra"]["nome"]
        output_path = ROOT / "tests" / "output" / "pipeline_invalido.docx"
        validate_mock.side_effect = MemorialValidationError(
            [
                ValidationIssue(
                    path="$.obra",
                    message="'nome' is a required property",
                    validator="required",
                )
            ]
        )

        with self.assertRaises(MemorialValidationError):
            generate_memorial_eletrico_v1(payload, output_path)

        validate_mock.assert_called_once()
        render_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
