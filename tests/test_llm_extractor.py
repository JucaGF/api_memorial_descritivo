from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services.llm_extractor import (
    EnergiaExtraction,
    GeradorExtraction,
    LLMExtraction,
    ObraExtraction,
    _merge_partials,
    extract_with_llm,
    is_llm_extraction_enabled,
)
from app.services.project_extractor import ExtractedSourceFile


def _source_file(name: str = "prancha.pdf", text: str = "TEXTO") -> ExtractedSourceFile:
    return ExtractedSourceFile(
        original_filename=name,
        stored_filename=f"01_{name}",
        extension=".pdf",
        saved_path=f"/tmp/01_{name}",
        extracted_text=text,
    )


class LLMExtractionSchemaTests(unittest.TestCase):
    def test_defaults_are_all_none(self) -> None:
        extraction = LLMExtraction()
        dumped = extraction.model_dump(mode="json")

        for section_key in ("obra", "energia", "aterramento", "mt", "gerador"):
            section = dumped[section_key]
            for field_key, value in section.items():
                self.assertIsNone(value, f"{section_key}.{field_key} should default to None")

        self.assertIsNone(dumped["observacoes"])

    def test_energia_accepts_new_fields(self) -> None:
        energia = EnergiaExtraction(
            potencia_transformador_kva=500.0,
            tap_descricao="tap nominal",
            tensao_secundaria="220/127V",
        )
        self.assertEqual(energia.potencia_transformador_kva, 500.0)
        self.assertEqual(energia.tap_descricao, "tap nominal")
        self.assertEqual(energia.tensao_secundaria, "220/127V")

    def test_gerador_accepts_circuitos_atendidos(self) -> None:
        gerador = GeradorExtraction(
            tipo_atendimento="parcial",
            circuitos_atendidos="elevadores, bombas",
        )
        self.assertEqual(gerador.circuitos_atendidos, "elevadores, bombas")

    def test_full_extraction_round_trip(self) -> None:
        extraction = LLMExtraction(
            obra=ObraExtraction(construtora="Teste LTDA"),
            energia=EnergiaExtraction(tem_subestacao=True, potencia_transformador_kva=1000),
            gerador=GeradorExtraction(tipo_atendimento="parcial", circuitos_atendidos="bombas"),
        )
        dumped = extraction.model_dump(mode="json")
        restored = LLMExtraction.model_validate(dumped)
        self.assertEqual(restored.obra.construtora, "Teste LTDA")
        self.assertEqual(restored.energia.potencia_transformador_kva, 1000)
        self.assertEqual(restored.gerador.circuitos_atendidos, "bombas")


class MergePartialsTests(unittest.TestCase):
    def test_first_non_null_wins(self) -> None:
        p1 = {"obra": {"construtora": "Alpha", "nome": None}}
        p2 = {"obra": {"construtora": "Beta", "nome": "Edifício X"}}

        merged = _merge_partials([p1, p2])

        self.assertEqual(merged["obra"]["construtora"], "Alpha")
        self.assertEqual(merged["obra"]["nome"], "Edifício X")

    def test_observacoes_ignored(self) -> None:
        p1 = {"observacoes": "nota parcial", "obra": {"construtora": "A"}}
        merged = _merge_partials([p1])
        self.assertNotIn("observacoes", merged)

    def test_empty_partials(self) -> None:
        self.assertEqual(_merge_partials([]), {})
        self.assertEqual(_merge_partials([{}]), {})

    def test_multiple_sections(self) -> None:
        p1 = {"obra": {"construtora": "A"}, "energia": {"tem_subestacao": True}}
        p2 = {"energia": {"tipo_subestacao": "abrigada"}, "mt": {"tensao_kv": 13.8}}

        merged = _merge_partials([p1, p2])

        self.assertEqual(merged["obra"]["construtora"], "A")
        self.assertTrue(merged["energia"]["tem_subestacao"])
        self.assertEqual(merged["energia"]["tipo_subestacao"], "abrigada")
        self.assertEqual(merged["mt"]["tensao_kv"], 13.8)

    def test_non_dict_section_skipped(self) -> None:
        p1 = {"obra": {"construtora": "A"}, "stray_string": "hello"}
        merged = _merge_partials([p1])
        self.assertNotIn("stray_string", merged)


class IsLLMExtractionEnabledTests(unittest.TestCase):
    def test_returns_false_when_empty(self) -> None:
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": ""}):
            self.assertFalse(is_llm_extraction_enabled())

    def test_returns_false_when_whitespace(self) -> None:
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "   "}):
            self.assertFalse(is_llm_extraction_enabled())

    def test_returns_true_when_set(self) -> None:
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            self.assertTrue(is_llm_extraction_enabled())

    def test_returns_false_when_unset(self) -> None:
        env = os.environ.copy()
        env.pop("USE_LLM_EXTRACTION", None)
        with patch.dict(os.environ, env, clear=True):
            self.assertFalse(is_llm_extraction_enabled())


class ExtractWithLLMTests(unittest.TestCase):
    def test_returns_empty_when_disabled(self) -> None:
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": ""}):
            result = extract_with_llm([_source_file()])
        self.assertEqual(result, {})

    def test_returns_empty_when_no_text(self) -> None:
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            empty_file = _source_file(text="   ")
            result = extract_with_llm([empty_file])
        self.assertEqual(result, {})

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-4.1")
    def test_calls_client_and_returns_merged(self, _model_mock, client_mock) -> None:
        mock_parsed = LLMExtraction(
            obra=ObraExtraction(construtora="Teste Eng"),
            energia=EnergiaExtraction(tem_subestacao=True, potencia_transformador_kva=750),
        )
        mock_response = MagicMock()
        mock_response.output_parsed = mock_parsed
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_with_llm([_source_file()])

        mock_client.responses.parse.assert_called_once()
        self.assertEqual(result["obra"]["construtora"], "Teste Eng")
        self.assertTrue(result["energia"]["tem_subestacao"])
        self.assertEqual(result["energia"]["potencia_transformador_kva"], 750)

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-4.1")
    def test_handles_null_parse_response(self, _model_mock, client_mock) -> None:
        mock_response = MagicMock()
        mock_response.output_parsed = None
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_with_llm([_source_file()])

        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
