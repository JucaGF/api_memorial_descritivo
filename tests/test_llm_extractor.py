from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from app.services.llm_extractor import (
    EnergiaExtraction,
    GasNaturalLLMExtraction,
    GlpLLMExtraction,
    GeradorExtraction,
    InstalacaoExtraction,
    LLMExtraction,
    NaoInclusosExtraction,
    ObraExtraction,
    TelecomLLMExtraction,
    _build_gas_natural_text_only_input,
    _build_gas_natural_vision_input,
    _build_glp_text_only_input,
    _build_glp_vision_input,
    _build_telecom_text_only_input,
    _build_telecom_vision_input,
    _build_text_only_input,
    _build_vision_input,
    _first_non_null_merge,
    extract_gas_natural_with_llm,
    extract_glp_with_llm,
    extract_telecom_with_llm,
    extract_with_llm,
    is_llm_extraction_enabled,
)
from app.services.project_extractor import ExtractedSourceFile


def _source_file(
    name: str = "prancha.pdf",
    text: str = "TEXTO",
    page_images: list[str] | None = None,
) -> ExtractedSourceFile:
    return ExtractedSourceFile(
        original_filename=name,
        stored_filename=f"01_{name}",
        extension=".pdf",
        saved_path=f"/tmp/01_{name}",
        extracted_text=text,
        page_images=page_images or [],
    )


class LLMExtractionSchemaTests(unittest.TestCase):
    def test_defaults_are_all_none(self) -> None:
        extraction = LLMExtraction()
        dumped = extraction.model_dump(mode="json")

        for section_key in ("obra", "energia", "aterramento", "mt", "gerador",
                            "nao_inclusos", "instalacao"):
            section = dumped[section_key]
            for field_key, value in section.items():
                self.assertIsNone(value, f"{section_key}.{field_key} should default to None")

        self.assertIsNone(dumped["observacoes"])

    def test_energia_accepts_fields(self) -> None:
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

    def test_nao_inclusos_schema(self) -> None:
        nao_inclusos = NaoInclusosExtraction(cftv=False, alarme_incendio=True)
        self.assertFalse(nao_inclusos.cftv)
        self.assertTrue(nao_inclusos.alarme_incendio)
        self.assertIsNone(nao_inclusos.cpct)

    def test_instalacao_schema(self) -> None:
        instalacao = InstalacaoExtraction(perfilado_tipo="C 38x38mm")
        self.assertEqual(instalacao.perfilado_tipo, "C 38x38mm")

    def test_obra_has_qtd_apartamentos(self) -> None:
        obra = ObraExtraction(qtd_apartamentos=120)
        self.assertEqual(obra.qtd_apartamentos, 120)

    def test_full_extraction_round_trip(self) -> None:
        extraction = LLMExtraction(
            obra=ObraExtraction(construtora="Teste LTDA"),
            energia=EnergiaExtraction(tem_subestacao=True, potencia_transformador_kva=1000),
            gerador=GeradorExtraction(tipo_atendimento="parcial", circuitos_atendidos="bombas"),
            nao_inclusos=NaoInclusosExtraction(cftv=False),
            instalacao=InstalacaoExtraction(perfilado_tipo="C 38x38mm"),
        )
        dumped = extraction.model_dump(mode="json")
        restored = LLMExtraction.model_validate(dumped)
        self.assertEqual(restored.obra.construtora, "Teste LTDA")
        self.assertEqual(restored.energia.potencia_transformador_kva, 1000)
        self.assertEqual(restored.gerador.circuitos_atendidos, "bombas")
        self.assertFalse(restored.nao_inclusos.cftv)
        self.assertEqual(restored.instalacao.perfilado_tipo, "C 38x38mm")

    def test_telecom_schema_defaults_are_none(self) -> None:
        extraction = TelecomLLMExtraction()
        dumped = extraction.model_dump(mode="json")

        for field_key, value in dumped["obra"].items():
            self.assertIsNone(value, f"obra.{field_key} should default to None")
        self.assertIsNone(dumped["observacoes"])

    def test_gas_natural_schema_defaults_are_none(self) -> None:
        extraction = GasNaturalLLMExtraction()
        dumped = extraction.model_dump(mode="json")

        for section_key in (
            "obra",
            "crm",
            "dimensionamento",
            "soma",
            "ramal",
            "valvula",
            "numero",
        ):
            section = dumped[section_key]
            for field_key, value in section.items():
                self.assertIsNone(value, f"{section_key}.{field_key} should default to None")
        self.assertIsNone(dumped["teto_ou_piso"])
        self.assertIsNone(dumped["observacoes"])


class VisionInputTests(unittest.TestCase):
    def test_build_vision_input_includes_images_and_text(self) -> None:
        sf = _source_file(
            text="OCR text",
            page_images=["data:image/png;base64,AAA", "data:image/png;base64,BBB"],
        )
        messages = _build_vision_input(sf)

        self.assertEqual(len(messages), 1)
        content = messages[0]["content"]
        image_parts = [p for p in content if p["type"] == "input_image"]
        text_parts = [p for p in content if p["type"] == "input_text"]

        self.assertEqual(len(image_parts), 2)
        self.assertEqual(image_parts[0]["detail"], "original")
        self.assertTrue(any("OCR text" in p["text"] for p in text_parts))

    def test_build_vision_input_skips_empty_text(self) -> None:
        sf = _source_file(text="   ", page_images=["data:image/png;base64,AAA"])
        messages = _build_vision_input(sf)

        content = messages[0]["content"]
        text_parts = [p for p in content if p["type"] == "input_text"]
        self.assertEqual(len(text_parts), 1)

    def test_build_text_only_input_has_no_images(self) -> None:
        sf = _source_file(text="Some text")
        messages = _build_text_only_input(sf)

        content = messages[0]["content"]
        image_parts = [p for p in content if p.get("type") == "input_image"]
        self.assertEqual(len(image_parts), 0)

    def test_build_telecom_vision_input_includes_images_and_text(self) -> None:
        sf = _source_file(
            text="OCR telecom text",
            page_images=["data:image/png;base64,AAA"],
        )
        messages = _build_telecom_vision_input(sf)

        content = messages[0]["content"]
        image_parts = [p for p in content if p["type"] == "input_image"]
        text_parts = [p for p in content if p["type"] == "input_text"]

        self.assertEqual(len(image_parts), 1)
        self.assertTrue(any("OCR telecom text" in p["text"] for p in text_parts))

    def test_build_telecom_text_only_input_has_no_images(self) -> None:
        sf = _source_file(text="Some telecom text")
        messages = _build_telecom_text_only_input(sf)

        content = messages[0]["content"]
        image_parts = [p for p in content if p.get("type") == "input_image"]
        self.assertEqual(len(image_parts), 0)

    def test_build_gas_natural_vision_input_includes_images_and_text(self) -> None:
        sf = _source_file(
            text="OCR gas natural text",
            page_images=["data:image/png;base64,AAA"],
        )
        messages = _build_gas_natural_vision_input(sf)

        content = messages[0]["content"]
        image_parts = [p for p in content if p["type"] == "input_image"]
        text_parts = [p for p in content if p["type"] == "input_text"]

        self.assertEqual(len(image_parts), 1)
        self.assertTrue(any("OCR gas natural text" in p["text"] for p in text_parts))

    def test_build_gas_natural_text_only_input_has_no_images(self) -> None:
        sf = _source_file(text="Some gas natural text")
        messages = _build_gas_natural_text_only_input(sf)

        content = messages[0]["content"]
        image_parts = [p for p in content if p.get("type") == "input_image"]
        self.assertEqual(len(image_parts), 0)

    def test_build_glp_vision_input_includes_images_and_text(self) -> None:
        sf = _source_file(
            text="OCR glp text",
            page_images=["data:image/png;base64,AAA"],
        )
        messages = _build_glp_vision_input(sf)

        content = messages[0]["content"]
        image_parts = [p for p in content if p["type"] == "input_image"]
        text_parts = [p for p in content if p["type"] == "input_text"]

        self.assertEqual(len(image_parts), 1)
        self.assertTrue(any("OCR glp text" in p["text"] for p in text_parts))

    def test_build_glp_text_only_input_has_no_images(self) -> None:
        sf = _source_file(text="Some glp text")
        messages = _build_glp_text_only_input(sf)

        content = messages[0]["content"]
        image_parts = [p for p in content if p.get("type") == "input_image"]
        self.assertEqual(len(image_parts), 0)


class FirstNonNullMergeTests(unittest.TestCase):
    def test_first_non_null_wins(self) -> None:
        p1 = {"obra": {"construtora": "Alpha", "nome": None}}
        p2 = {"obra": {"construtora": "Beta", "nome": "Edifício X"}}

        merged = _first_non_null_merge([p1, p2])

        self.assertEqual(merged["obra"]["construtora"], "Alpha")
        self.assertEqual(merged["obra"]["nome"], "Edifício X")

    def test_observacoes_ignored(self) -> None:
        p1 = {"observacoes": "nota parcial", "obra": {"construtora": "A"}}
        merged = _first_non_null_merge([p1])
        self.assertNotIn("observacoes", merged)

    def test_empty_partials(self) -> None:
        self.assertEqual(_first_non_null_merge([]), {})
        self.assertEqual(_first_non_null_merge([{}]), {})

    def test_multiple_sections(self) -> None:
        p1 = {"obra": {"construtora": "A"}, "energia": {"tem_subestacao": True}}
        p2 = {"energia": {"tipo_subestacao": "abrigada"}, "mt": {"tensao_kv": 13.8}}

        merged = _first_non_null_merge([p1, p2])

        self.assertEqual(merged["obra"]["construtora"], "A")
        self.assertTrue(merged["energia"]["tem_subestacao"])
        self.assertEqual(merged["energia"]["tipo_subestacao"], "abrigada")
        self.assertEqual(merged["mt"]["tensao_kv"], 13.8)

    def test_non_dict_section_skipped(self) -> None:
        p1 = {"obra": {"construtora": "A"}, "stray_string": "hello"}
        merged = _first_non_null_merge([p1])
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

    def test_returns_empty_when_no_content(self) -> None:
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            empty_file = _source_file(text="   ", page_images=[])
            result = extract_with_llm([empty_file])
        self.assertEqual(result, {})

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_single_file_extraction(self, _model_mock, client_mock) -> None:
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
        self.assertNotIn("observacoes", result)

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_vision_input_used_for_files_with_images(self, _model_mock, client_mock) -> None:
        mock_parsed = LLMExtraction(obra=ObraExtraction(construtora="Visual"))
        mock_response = MagicMock()
        mock_response.output_parsed = mock_parsed
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        sf = _source_file(page_images=["data:image/png;base64,AAA"])
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            extract_with_llm([sf])

        call_kwargs = mock_client.responses.parse.call_args
        self.assertIn("reasoning", call_kwargs.kwargs)

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_multiple_files_triggers_merge(self, _model_mock, client_mock) -> None:
        extraction_a = LLMExtraction(obra=ObraExtraction(construtora="Alpha"))
        extraction_b = LLMExtraction(energia=EnergiaExtraction(tem_subestacao=True))
        merged_result = LLMExtraction(
            obra=ObraExtraction(construtora="Alpha"),
            energia=EnergiaExtraction(tem_subestacao=True),
        )

        response_a = MagicMock()
        response_a.output_parsed = extraction_a
        response_b = MagicMock()
        response_b.output_parsed = extraction_b
        merge_response = MagicMock()
        merge_response.output_parsed = merged_result

        mock_client = MagicMock()
        mock_client.responses.parse.side_effect = [response_a, response_b, merge_response]
        client_mock.return_value = mock_client

        files = [_source_file("a.pdf", "text a"), _source_file("b.pdf", "text b")]
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_with_llm(files)

        self.assertEqual(mock_client.responses.parse.call_count, 3)
        self.assertEqual(result["obra"]["construtora"], "Alpha")
        self.assertTrue(result["energia"]["tem_subestacao"])

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_multiple_rich_text_files_use_single_combined_extraction(
        self,
        _model_mock,
        client_mock,
    ) -> None:
        mock_parsed = LLMExtraction(obra=ObraExtraction(construtora="Combined"))
        mock_response = MagicMock()
        mock_response.output_parsed = mock_parsed
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        files = [
            _source_file("a.pdf", "EL " * 2000, ["data:image/png;base64,AAA"]),
            _source_file("b.pdf", "EL " * 2000, ["data:image/png;base64,BBB"]),
        ]
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_with_llm(files)

        kwargs = mock_client.responses.parse.call_args.kwargs
        content = kwargs["input"][0]["content"]
        self.assertEqual(mock_client.responses.parse.call_count, 1)
        self.assertFalse(any(part.get("type") == "input_image" for part in content))
        self.assertNotIn("reasoning", kwargs)
        self.assertEqual(result["obra"]["construtora"], "Combined")

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_handles_null_parse_response(self, _model_mock, client_mock) -> None:
        mock_response = MagicMock()
        mock_response.output_parsed = None
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_with_llm([_source_file()])

        self.assertEqual(result, {})

    def test_extract_telecom_returns_empty_when_disabled(self) -> None:
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": ""}):
            result = extract_telecom_with_llm([_source_file()])
        self.assertEqual(result, {})

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_single_file_telecom_extraction(self, _model_mock, client_mock) -> None:
        mock_parsed = TelecomLLMExtraction(
            obra=ObraExtraction(
                construtora="Teste Telecom",
                nome="Residencial Fibra",
                qtd_lojas=2,
            )
        )
        mock_response = MagicMock()
        mock_response.output_parsed = mock_parsed
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_telecom_with_llm([_source_file()])

        mock_client.responses.parse.assert_called_once()
        self.assertEqual(result["obra"]["construtora"], "Teste Telecom")
        self.assertEqual(result["obra"]["nome"], "Residencial Fibra")
        self.assertEqual(result["obra"]["qtd_lojas"], 2)
        self.assertNotIn("observacoes", result)

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_multiple_files_triggers_telecom_merge(self, _model_mock, client_mock) -> None:
        extraction_a = TelecomLLMExtraction(obra=ObraExtraction(construtora="Alpha"))
        extraction_b = TelecomLLMExtraction(obra=ObraExtraction(qtd_lojas=3))
        merged_result = TelecomLLMExtraction(
            obra=ObraExtraction(construtora="Alpha", qtd_lojas=3)
        )

        response_a = MagicMock()
        response_a.output_parsed = extraction_a
        response_b = MagicMock()
        response_b.output_parsed = extraction_b
        merge_response = MagicMock()
        merge_response.output_parsed = merged_result

        mock_client = MagicMock()
        mock_client.responses.parse.side_effect = [response_a, response_b, merge_response]
        client_mock.return_value = mock_client

        files = [_source_file("a.pdf", "text a"), _source_file("b.pdf", "text b")]
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_telecom_with_llm(files)

        self.assertEqual(mock_client.responses.parse.call_count, 3)
        self.assertEqual(result["obra"]["construtora"], "Alpha")
        self.assertEqual(result["obra"]["qtd_lojas"], 3)

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_telecom_multiple_rich_text_files_use_single_combined_extraction(
        self,
        _model_mock,
        client_mock,
    ) -> None:
        mock_parsed = TelecomLLMExtraction(obra=ObraExtraction(construtora="Telecom Combined"))
        mock_response = MagicMock()
        mock_response.output_parsed = mock_parsed
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        files = [
            _source_file("a.pdf", "TELECOM " * 1000, ["data:image/png;base64,AAA"]),
            _source_file("b.pdf", "TELECOM " * 1000, ["data:image/png;base64,BBB"]),
        ]
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_telecom_with_llm(files)

        kwargs = mock_client.responses.parse.call_args.kwargs
        content = kwargs["input"][0]["content"]
        self.assertEqual(mock_client.responses.parse.call_count, 1)
        self.assertFalse(any(part.get("type") == "input_image" for part in content))
        self.assertNotIn("reasoning", kwargs)
        self.assertEqual(result["obra"]["construtora"], "Telecom Combined")

    def test_extract_gas_natural_returns_empty_when_disabled(self) -> None:
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": ""}):
            result = extract_gas_natural_with_llm([_source_file()])
        self.assertEqual(result, {})

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_single_file_gas_natural_extraction(self, _model_mock, client_mock) -> None:
        mock_parsed = GasNaturalLLMExtraction(
            obra=ObraExtraction(
                construtora="Teste Gas",
                nome="Residencial Gas",
            )
        )
        mock_response = MagicMock()
        mock_response.output_parsed = mock_parsed
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_gas_natural_with_llm([_source_file()])

        mock_client.responses.parse.assert_called_once()
        self.assertEqual(result["obra"]["construtora"], "Teste Gas")
        self.assertEqual(result["obra"]["nome"], "Residencial Gas")
        self.assertNotIn("observacoes", result)

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_multiple_files_triggers_gas_natural_merge(self, _model_mock, client_mock) -> None:
        extraction_a = GasNaturalLLMExtraction(obra=ObraExtraction(construtora="Alpha"))
        extraction_b = GasNaturalLLMExtraction(valvula={"esfera_diametro": "32 mm"})
        merged_result = GasNaturalLLMExtraction(
            obra=ObraExtraction(construtora="Alpha"),
            valvula={"esfera_diametro": "32 mm"},
        )

        response_a = MagicMock()
        response_a.output_parsed = extraction_a
        response_b = MagicMock()
        response_b.output_parsed = extraction_b
        merge_response = MagicMock()
        merge_response.output_parsed = merged_result

        mock_client = MagicMock()
        mock_client.responses.parse.side_effect = [response_a, response_b, merge_response]
        client_mock.return_value = mock_client

        files = [_source_file("a.pdf", "text a"), _source_file("b.pdf", "text b")]
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_gas_natural_with_llm(files)

        self.assertEqual(mock_client.responses.parse.call_count, 3)
        self.assertEqual(result["obra"]["construtora"], "Alpha")
        self.assertEqual(result["valvula"]["esfera_diametro"], "32 mm")

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_gas_natural_multiple_rich_text_files_use_single_combined_extraction(
        self,
        _model_mock,
        client_mock,
    ) -> None:
        mock_parsed = GasNaturalLLMExtraction(obra=ObraExtraction(construtora="Gas Combined"))
        mock_response = MagicMock()
        mock_response.output_parsed = mock_parsed
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        files = [
            _source_file("a.pdf", "GAS " * 2000, ["data:image/png;base64,AAA"]),
            _source_file("b.pdf", "GAS " * 2000, ["data:image/png;base64,BBB"]),
        ]
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_gas_natural_with_llm(files)

        kwargs = mock_client.responses.parse.call_args.kwargs
        content = kwargs["input"][0]["content"]
        self.assertEqual(mock_client.responses.parse.call_count, 1)
        self.assertFalse(any(part.get("type") == "input_image" for part in content))
        self.assertNotIn("reasoning", kwargs)
        self.assertEqual(result["obra"]["construtora"], "Gas Combined")

    def test_extract_glp_returns_empty_when_disabled(self) -> None:
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": ""}):
            result = extract_glp_with_llm([_source_file()])
        self.assertEqual(result, {})

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_glp_rich_text_pdf_prefers_text_only_input(self, _model_mock, client_mock) -> None:
        mock_parsed = GlpLLMExtraction(obra=ObraExtraction(construtora="GLP Textual"))
        mock_response = MagicMock()
        mock_response.output_parsed = mock_parsed
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        sf = _source_file(
            text="GLP " * 1000,
            page_images=["data:image/png;base64,AAA"],
        )
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            extract_glp_with_llm([sf])

        kwargs = mock_client.responses.parse.call_args.kwargs
        content = kwargs["input"][0]["content"]
        self.assertFalse(any(part.get("type") == "input_image" for part in content))
        self.assertNotIn("reasoning", kwargs)

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_glp_short_text_pdf_keeps_vision_input(self, _model_mock, client_mock) -> None:
        mock_parsed = GlpLLMExtraction(obra=ObraExtraction(construtora="GLP Visual"))
        mock_response = MagicMock()
        mock_response.output_parsed = mock_parsed
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        sf = _source_file(
            text="texto curto",
            page_images=["data:image/png;base64,AAA"],
        )
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            extract_glp_with_llm([sf])

        kwargs = mock_client.responses.parse.call_args.kwargs
        content = kwargs["input"][0]["content"]
        self.assertTrue(any(part.get("type") == "input_image" for part in content))
        self.assertIn("reasoning", kwargs)

    @patch("app.services.llm_extractor._get_client")
    @patch("app.services.llm_extractor._get_model", return_value="gpt-5.4")
    def test_glp_multiple_rich_text_files_use_single_combined_extraction(
        self,
        _model_mock,
        client_mock,
    ) -> None:
        mock_parsed = GlpLLMExtraction(obra=ObraExtraction(construtora="GLP Combined"))
        mock_response = MagicMock()
        mock_response.output_parsed = mock_parsed
        mock_client = MagicMock()
        mock_client.responses.parse.return_value = mock_response
        client_mock.return_value = mock_client

        files = [
            _source_file("a.pdf", "GLP " * 1000, ["data:image/png;base64,AAA"]),
            _source_file("b.pdf", "GLP " * 1000, ["data:image/png;base64,BBB"]),
        ]
        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result = extract_glp_with_llm(files)

        self.assertEqual(mock_client.responses.parse.call_count, 1)
        self.assertEqual(result["obra"]["construtora"], "GLP Combined")


if __name__ == "__main__":
    unittest.main()
