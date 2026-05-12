from __future__ import annotations

import io
import os
from pathlib import Path
from tempfile import mkdtemp
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import UploadFile

from app.services.extraction_mapper import ExtractionReport, MappingResult
from app.services.file_ingestion import FileIngestionResult, IngestedFileMetadata
from app.services.memorial_validator import MemorialValidationError, ValidationIssue
from app.services.pipeline import PipelineResult
from app.services.llm_extractor import LLMExtractionRunResult
from app.services.pipeline_from_files import (
    _build_extraction_report_payload,
    _normalize_gas_natural_context,
    _normalize_glp_context,
    _fill_gaps,
    extract_mapping_from_ingested_files,
    extract_glp_mapping_from_ingested_files,
    extract_gas_natural_mapping_from_ingested_files,
    extract_telecom_mapping_from_ingested_files,
    generate_memorial_eletrico_v1_from_ingested_files,
    generate_memorial_gas_natural_v1_from_ingested_files,
    generate_memorial_gas_natural_v1_from_uploaded_files,
    generate_memorial_glp_v1_from_ingested_files,
    generate_memorial_telecom_v1_from_ingested_files,
    generate_memorial_telecom_v1_from_uploaded_files,
    generate_memorial_eletrico_v1_from_uploaded_files,
)
from app.services.project_extractor import ExtractedSourceFile, ProjectExtractionResult


ROOT = Path(__file__).resolve().parent.parent


def build_ingested_file() -> IngestedFileMetadata:
    return IngestedFileMetadata(
        original_filename="projeto.docx",
        stored_filename="01_projeto.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        extension=".docx",
        size_bytes=1024,
        saved_path="/tmp/01_projeto.docx",
    )


def build_extraction_result() -> ProjectExtractionResult:
    return ProjectExtractionResult(
        raw_text="CONSTRUTORA: Exemplo Engenharia LTDA",
        source_files=[],
        signals={"total_files": 1},
    )


def build_extracted_source_file(filename: str) -> ExtractedSourceFile:
    return ExtractedSourceFile(
        original_filename=filename,
        stored_filename=filename,
        extension=".pdf",
        saved_path=f"/tmp/{filename}",
        extracted_text="",
    )


def build_mapping_result(partial_context: dict | None = None) -> MappingResult:
    context = partial_context or {"obra": {"construtora": "Exemplo Engenharia LTDA"}}
    return MappingResult(context=context, evidence={})


def build_extraction_report() -> ExtractionReport:
    return ExtractionReport(filled=["obra.construtora"], missing=[], pending=[])


class MapperOnlyPathTests(unittest.TestCase):
    """Tests for the mapper-only extraction path (LLM disabled)."""

    @patch("app.services.pipeline_from_files.assess_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_mapper_only_when_llm_disabled(
        self,
        extract_mock,
        map_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        mapping = build_mapping_result()
        report = build_extraction_report()

        extract_mock.return_value = build_extraction_result()
        map_mock.return_value = mapping
        assess_mock.return_value = report

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": ""}):
            result_mapping, result_report = extract_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping, mapping)
        self.assertEqual(result_report, report)
        extract_mock.assert_called_once_with(ingested_files)
        map_mock.assert_called_once()
        assess_mock.assert_called_once()


class ExtractionReportPayloadTests(unittest.TestCase):
    def test_build_extraction_report_payload_keeps_cross_validation_details(self) -> None:
        report = ExtractionReport(
            filled=["obra.construtora"],
            missing=[],
            pending=[],
            cross_validation={
                "batch_size": 5,
                "batch_count": 3,
                "candidate_count": 7,
                "resolved_fields": ["obra.construtora"],
                "conflicts": [{"field_path": "obra.construtora"}],
                "fallback_used": True,
            },
        )

        payload = _build_extraction_report_payload(
            report,
            conflicts=[{"type": "glp_total_points_conflict"}],
        )

        self.assertEqual(payload["cross_validation"]["batch_size"], 5)
        self.assertTrue(payload["cross_validation"]["fallback_used"])
        self.assertEqual(payload["conflicts"], [{"type": "glp_total_points_conflict"}])


class LLMPrimaryPathTests(unittest.TestCase):
    """Tests for the LLM-primary extraction path."""

    @patch("app.services.pipeline_from_files.assess_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_context")
    @patch("app.services.pipeline_from_files.extract_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_llm_primary_uses_llm_as_base(
        self,
        extract_files_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        llm_context = {
            "obra": {"construtora": "LLM Corp", "nome": "Edifício LLM"},
            "energia": {"tem_subestacao": True},
        }
        mapper_mapping = build_mapping_result({"obra": {"construtora": "Mapper Corp"}})
        report = build_extraction_report()

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        map_mock.return_value = mapper_mapping
        assess_mock.return_value = report

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, _ = extract_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping.context["obra"]["construtora"], "LLM Corp")
        self.assertEqual(result_mapping.context["obra"]["nome"], "Edifício LLM")

    @patch("app.services.pipeline_from_files.assess_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_context")
    @patch("app.services.pipeline_from_files.extract_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_mapper_supplements_llm_gaps(
        self,
        extract_files_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        llm_context = {"obra": {"construtora": "LLM Corp", "nome": None}}
        mapper_mapping = build_mapping_result(
            {"obra": {"construtora": "Mapper Corp", "nome": "Edifício Mapper"}}
        )
        report = build_extraction_report()

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        map_mock.return_value = mapper_mapping
        assess_mock.return_value = report

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, _ = extract_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping.context["obra"]["construtora"], "LLM Corp")
        self.assertEqual(result_mapping.context["obra"]["nome"], "Edifício Mapper")

    @patch("app.services.pipeline_from_files.map_extraction_to_partial_context")
    @patch("app.services.pipeline_from_files.extract_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_eletrico_llm_failure_stops_generation(
        self,
        extract_files_mock,
        extract_llm_mock,
        map_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.side_effect = RuntimeError("OpenAI request failed")

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            with self.assertRaisesRegex(RuntimeError, "OpenAI request failed"):
                extract_mapping_from_ingested_files(ingested_files)

        map_mock.assert_not_called()

    @patch("app.services.pipeline_from_files.assess_telecom_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_telecom_context")
    @patch("app.services.pipeline_from_files.extract_telecom_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_telecom_llm_primary_uses_llm_as_base(
        self,
        extract_files_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        llm_context = {
            "obra": {"construtora": "LLM Telecom", "nome": "Edifício LLM", "qtd_lojas": 2},
        }
        mapper_mapping = build_mapping_result({"obra": {"construtora": "Mapper Corp"}})
        report = build_extraction_report()

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        map_mock.return_value = mapper_mapping
        assess_mock.return_value = report

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, _ = extract_telecom_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping.context["obra"]["construtora"], "LLM Telecom")
        self.assertEqual(result_mapping.context["obra"]["nome"], "Edifício LLM")
        self.assertEqual(result_mapping.context["obra"]["qtd_lojas"], 2)

    @patch("app.services.pipeline_from_files.assess_telecom_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_telecom_context")
    @patch("app.services.pipeline_from_files.extract_telecom_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_telecom_mapper_supplements_llm_gaps(
        self,
        extract_files_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        llm_context = {"obra": {"construtora": "LLM Telecom", "nome": None}}
        mapper_mapping = build_mapping_result(
            {"obra": {"construtora": "Mapper Corp", "nome": "Edifício Mapper"}}
        )
        report = build_extraction_report()

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        map_mock.return_value = mapper_mapping
        assess_mock.return_value = report

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, _ = extract_telecom_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping.context["obra"]["construtora"], "LLM Telecom")
        self.assertEqual(result_mapping.context["obra"]["nome"], "Edifício Mapper")

    @patch("app.services.pipeline_from_files.assess_gas_natural_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_gas_natural_context")
    @patch("app.services.pipeline_from_files.extract_gas_natural_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_gas_natural_llm_primary_uses_llm_as_base(
        self,
        extract_files_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        llm_context = {
            "obra": {"construtora": "LLM Gas", "nome": "Edifício LLM"},
            "valvula": {"esfera_diametro": "32 mm"},
        }
        mapper_mapping = build_mapping_result({"obra": {"construtora": "Mapper Corp"}})
        report = build_extraction_report()

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        map_mock.return_value = mapper_mapping
        assess_mock.return_value = report

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, _ = extract_gas_natural_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping.context["obra"]["construtora"], "LLM Gas")
        self.assertEqual(result_mapping.context["obra"]["nome"], "Edifício LLM")
        self.assertEqual(result_mapping.context["valvula"]["esfera_diametro"], "32 mm")

    @patch("app.services.pipeline_from_files.assess_gas_natural_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_gas_natural_context")
    @patch("app.services.pipeline_from_files.extract_gas_natural_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_gas_natural_mapper_supplements_llm_gaps(
        self,
        extract_files_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        llm_context = {"obra": {"construtora": "LLM Gas", "nome": None}}
        mapper_mapping = build_mapping_result(
            {"obra": {"construtora": "Mapper Corp", "nome": "Edifício Mapper"}}
        )
        report = build_extraction_report()

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        map_mock.return_value = mapper_mapping
        assess_mock.return_value = report

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, _ = extract_gas_natural_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping.context["obra"]["construtora"], "LLM Gas")
        self.assertEqual(result_mapping.context["obra"]["nome"], "Edifício Mapper")

    @patch("app.services.pipeline_from_files.assess_gas_natural_extraction_coverage")
    @patch("app.services.pipeline_from_files.extract_gas_natural_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_gas_natural_mapper_fills_llm_null_typology_from_sheet_filenames(
        self,
        extract_files_mock,
        extract_llm_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = ProjectExtractionResult(
            raw_text="PROJETO DE INSTALAÇÕES DE GÁS NATURAL",
            source_files=[
                build_extracted_source_file("01_mga_mondo_g_s_01_subsolo_ao_3_pav_18_07_2023.pdf"),
                build_extracted_source_file("02_mga_mondo_g_s_02_4_e_5_pav_18_07_2023.pdf"),
                build_extracted_source_file("03_mga_mondo_g_s_03_6_pav_e_cobertura_18_07_2023.pdf"),
            ],
            signals={"total_files": 3},
        )
        llm_context = {
            "obra": {
                "construtora": "LLM Gas",
                "tipologia": None,
            },
        }

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        assess_mock.return_value = build_extraction_report()

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, _ = extract_gas_natural_mapping_from_ingested_files(ingested_files)

        self.assertEqual(
            result_mapping.context["obra"]["tipologia"],
            "Subsolo, 6 pavimentos, cobertura",
        )

    @patch("app.services.pipeline_from_files.assess_glp_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_glp_context")
    @patch("app.services.pipeline_from_files.extract_glp_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_glp_mapper_supplements_llm_gaps(
        self,
        extract_files_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        llm_context = {
            "obra": {
                "construtora": "LLM GLP",
                "nome": "Edifício LLM",
                "tipo_edificacao": None,
                "tipologia": None,
                "qtd_lojas": None,
                "qtd_restaurantes": None,
            },
            "dimensionamento": {"qtd_aquecedor": None},
        }
        mapper_mapping = build_mapping_result(
            {
                "obra": {
                    "tipo_edificacao": "Residencial Multifamiliar",
                    "tipologia": "Subsolo, térreo, 8 pavimentos, cobertura",
                    "qtd_lojas": 0,
                    "qtd_restaurantes": 0,
                },
                "dimensionamento": {"qtd_aquecedor": 0},
            }
        )
        report = build_extraction_report()

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        map_mock.return_value = mapper_mapping
        assess_mock.return_value = report

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, _ = extract_glp_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping.context["obra"]["construtora"], "LLM GLP")
        self.assertEqual(result_mapping.context["obra"]["tipo_edificacao"], "Residencial Multifamiliar")
        self.assertEqual(result_mapping.context["obra"]["qtd_lojas"], 0)
        self.assertEqual(result_mapping.context["dimensionamento"]["qtd_aquecedor"], 0)

    @patch("app.services.pipeline_from_files.assess_glp_extraction_coverage")
    @patch("app.services.pipeline_from_files.extract_glp_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_glp_mapper_extracts_appliance_counts_from_ocr_text_and_reconciles_total_points(
        self,
        extract_files_mock,
        extract_llm_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = ProjectExtractionResult(
            raw_text=(
                "DIMENSIONAMENTO GLP\n"
                "56 fogões\n"
                "0 aquecedores\n"
                "5 churrasqueiras\n"
            ),
            source_files=[],
            signals={"total_files": 1},
        )
        llm_context = {
            "obra": {"construtora": "LLM GLP"},
            "dimensionamento": {
                "qtd_fogao": None,
                "qtd_aquecedor": None,
                "qtd_churrasqueira": None,
            },
            "soma": {"qtd_pontos_de_utilizacao": 999},
        }
        report = build_extraction_report()

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        assess_mock.return_value = report

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, _ = extract_glp_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping.context["dimensionamento"]["qtd_fogao"], 56)
        self.assertEqual(result_mapping.context["dimensionamento"]["qtd_aquecedor"], 0)
        self.assertEqual(result_mapping.context["dimensionamento"]["qtd_churrasqueira"], 5)
        self.assertEqual(result_mapping.context["soma"]["qtd_pontos_de_utilizacao"], 61)
        self.assertEqual(result_mapping.evidence["dimensionamento.qtd_fogao"].value, 56)
        self.assertEqual(result_mapping.evidence["dimensionamento.qtd_aquecedor"].value, 0)
        self.assertEqual(result_mapping.evidence["dimensionamento.qtd_churrasqueira"].value, 5)

    @patch("app.services.pipeline_from_files.assess_glp_extraction_coverage")
    @patch("app.services.pipeline_from_files.extract_glp_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_glp_mapper_does_not_default_to_zero_for_appliance_mentions_without_numeric_evidence(
        self,
        extract_files_mock,
        extract_llm_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = ProjectExtractionResult(
            raw_text=(
                "DIMENSIONAMENTO GLP\n"
                "fogões previstos em projeto\n"
            ),
            source_files=[],
            signals={"total_files": 1},
        )
        llm_context = {
            "obra": {"construtora": "LLM GLP"},
            "dimensionamento": {
                "qtd_fogao": None,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 5,
            },
            "soma": {"qtd_pontos_de_utilizacao": 999},
        }
        report = build_extraction_report()

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        assess_mock.return_value = report

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, _ = extract_glp_mapping_from_ingested_files(ingested_files)

        self.assertIsNone(result_mapping.context["dimensionamento"].get("qtd_fogao"))
        self.assertNotIn("dimensionamento.qtd_fogao", result_mapping.evidence)
        self.assertEqual(result_mapping.context["soma"]["qtd_pontos_de_utilizacao"], 999)

    def test_normalize_glp_context_preserves_original_branch_diameter(self) -> None:
        context = {"ramal": {"primario_diametro": '1 1/4"'}}

        normalized = _normalize_glp_context(context)

        self.assertEqual(normalized["ramal"]["primario_diametro"], '1 1/4"')

    def test_normalize_glp_context_preserves_already_mm_string_input(self) -> None:
        context = {"ramal": {"primario_diametro": "32 mm"}}

        normalized = _normalize_glp_context(context)

        self.assertEqual(normalized["ramal"]["primario_diametro"], "32 mm")

    def test_normalize_gas_natural_context_normalizes_branch_fields(self) -> None:
        context = {
            "ramal": {
                "primario_diametro": '1 1/4"',
                "primario_pavimento": "TERREO",
            },
            "teto_ou_piso": "Pelo TETO",
        }

        normalized = _normalize_gas_natural_context(context)

        self.assertEqual(normalized["ramal"]["primario_diametro"], '1 1/4"')
        self.assertEqual(normalized["ramal"]["primario_pavimento"], "térreo")
        self.assertEqual(normalized["teto_ou_piso"], "teto")

    def test_normalize_gas_natural_context_derives_missing_total_from_complete_counts(
        self,
    ) -> None:
        context = {
            "dimensionamento": {
                "qtd_fogao": 4,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 1,
            },
            "soma": {"qtd_pontos_de_utilizacao": None},
        }

        normalized = _normalize_gas_natural_context(context)

        self.assertEqual(normalized["soma"]["qtd_pontos_de_utilizacao"], 5)

    def test_normalize_glp_context_preserves_total_points_when_dimensionamento_is_incomplete(
        self,
    ) -> None:
        cases = [
            {"qtd_fogao": 56, "qtd_aquecedor": None, "qtd_churrasqueira": 5},
            {"qtd_fogao": 56, "qtd_aquecedor": "0", "qtd_churrasqueira": 5},
        ]

        for dimensionamento in cases:
            with self.subTest(dimensionamento=dimensionamento):
                context = {
                    "dimensionamento": dimensionamento,
                    "soma": {"qtd_pontos_de_utilizacao": 999},
                }

                normalized = _normalize_glp_context(context)

                self.assertEqual(normalized["soma"]["qtd_pontos_de_utilizacao"], 999)

    def test_normalize_glp_context_leaves_unknown_ramal_location_values_unchanged(self) -> None:
        context = {
            "ramal": {"primario_pavimento": "Mezanino"},
            "teto_ou_piso": "Cobertura técnica",
        }

        normalized = _normalize_glp_context(context)

        self.assertEqual(normalized["ramal"]["primario_pavimento"], "Mezanino")
        self.assertEqual(normalized["teto_ou_piso"], "Cobertura técnica")

    def test_normalize_glp_context_canonicalizes_known_ramal_location_values(self) -> None:
        context = {
            "ramal": {"primario_pavimento": "TERREO"},
            "teto_ou_piso": "PISO",
        }

        normalized = _normalize_glp_context(context)

        self.assertEqual(normalized["ramal"]["primario_pavimento"], "térreo")
        self.assertEqual(normalized["teto_ou_piso"], "piso")

    @patch("app.services.pipeline_from_files.generate_memorial_glp_v1")
    @patch("app.services.pipeline_from_files.assess_glp_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_glp_context")
    @patch("app.services.pipeline_from_files.extract_glp_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_glp_pipeline_stops_before_render_when_total_points_conflict_is_unresolved(
        self,
        extract_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
        generate_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        output_path = ROOT / "tests" / "output" / "pipeline_from_files_glp_unresolved_conflict.docx"

        extract_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context={
            "obra": {"construtora": "LLM GLP"},
            "dimensionamento": {
                "qtd_fogao": 56,
                "qtd_aquecedor": None,
                "qtd_churrasqueira": 5,
            },
            "soma": {"qtd_pontos_de_utilizacao": 10},
        })
        map_mock.return_value = MappingResult(context={}, evidence={})
        assess_mock.return_value = build_extraction_report()
        generate_mock.return_value = PipelineResult(context={}, output_path=output_path)

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            with self.assertRaises(MemorialValidationError) as ctx:
                generate_memorial_glp_v1_from_ingested_files(ingested_files, output_path)

        generate_mock.assert_not_called()
        self.assertEqual(len(ctx.exception.issues), 1)
        self.assertEqual(ctx.exception.issues[0].path, "$.soma.qtd_pontos_de_utilizacao")
        self.assertEqual(ctx.exception.issues[0].validator, "glp_conflict")
        self.assertIsNotNone(ctx.exception.extraction_report)
        self.assertEqual(
            ctx.exception.extraction_report["conflicts"],
            [
                {
                    "type": "glp_total_points_conflict",
                    "status": "unresolved",
                    "field": "soma.qtd_pontos_de_utilizacao",
                    "reported_total": 10,
                    "dimensionamento_counts": {
                        "qtd_fogao": 56,
                        "qtd_aquecedor": None,
                        "qtd_churrasqueira": 5,
                    },
                    "known_dimensionamento_total": 61,
                    "deterministic_total": None,
                    "reason": "dimensionamento_incomplete",
                }
            ],
        )

    @patch("app.services.pipeline_from_files.generate_memorial_glp_v1")
    @patch("app.services.pipeline_from_files.assess_glp_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_glp_context")
    @patch("app.services.pipeline_from_files.extract_glp_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_glp_pipeline_records_resolved_total_points_conflict_in_error_report(
        self,
        extract_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
        generate_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        report = build_extraction_report()
        output_path = ROOT / "tests" / "output" / "pipeline_from_files_glp_resolved_conflict.docx"

        extract_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context={
            "obra": {"construtora": "LLM GLP"},
            "dimensionamento": {
                "qtd_fogao": 56,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 5,
            },
            "soma": {"qtd_pontos_de_utilizacao": 999},
        })
        map_mock.return_value = MappingResult(context={}, evidence={})
        assess_mock.return_value = report
        generate_mock.side_effect = MemorialValidationError(
            [ValidationIssue(path="$.obra", message="'tipologia' is a required property", validator="required")]
        )

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            with self.assertRaises(MemorialValidationError) as ctx:
                generate_memorial_glp_v1_from_ingested_files(ingested_files, output_path)

        generate_mock.assert_called_once()
        called_context = generate_mock.call_args.args[0]
        self.assertEqual(called_context["soma"]["qtd_pontos_de_utilizacao"], 61)
        self.assertIsNotNone(ctx.exception.extraction_report)
        self.assertEqual(
            ctx.exception.extraction_report["conflicts"],
            [
                {
                    "type": "glp_total_points_conflict",
                    "status": "resolved",
                    "field": "soma.qtd_pontos_de_utilizacao",
                    "reported_total": 999,
                    "dimensionamento_counts": {
                        "qtd_fogao": 56,
                        "qtd_aquecedor": 0,
                        "qtd_churrasqueira": 5,
                    },
                    "known_dimensionamento_total": 61,
                    "deterministic_total": 61,
                    "reason": "dimensionamento_complete",
                }
            ],
        )

    @patch("app.services.pipeline_from_files.generate_memorial_glp_v1")
    @patch("app.services.pipeline_from_files.assess_glp_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_glp_context")
    @patch("app.services.pipeline_from_files.extract_glp_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_glp_pipeline_prefers_table_sum_for_total_points_over_conflicting_isolated_value(
        self,
        extract_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
        generate_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        output_path = ROOT / "tests" / "output" / "pipeline_from_files_glp_total_points.docx"

        extract_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context={
            "obra": {"construtora": "LLM GLP"},
            "dimensionamento": {
                "qtd_fogao": 56,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 5,
            },
            "soma": {"qtd_pontos_de_utilizacao": 999},
            "ramal": {
                "primario_diametro": '1 1/4"',
                "primario_material": "aco carbono",
                "primario_pavimento": "TERREO",
            },
            "numero": {"prancha": "05/05"},
            "teto_ou_piso": "TETO",
        })
        map_mock.return_value = MappingResult(context={}, evidence={})
        assess_mock.return_value = build_extraction_report()
        generate_mock.return_value = PipelineResult(context={}, output_path=output_path)

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            generate_memorial_glp_v1_from_ingested_files(ingested_files, output_path)

        called_context = generate_mock.call_args.args[0]
        self.assertEqual(called_context["soma"]["qtd_pontos_de_utilizacao"], 61)
        self.assertEqual(called_context["dimensionamento"]["qtd_fogao"], 56)
        self.assertEqual(called_context["dimensionamento"]["qtd_aquecedor"], 0)
        self.assertEqual(called_context["dimensionamento"]["qtd_churrasqueira"], 5)


class GenerateFromIngestedFilesTests(unittest.TestCase):
    @patch("app.services.pipeline_from_files.generate_memorial_eletrico_v1")
    @patch("app.services.pipeline_from_files.assess_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_runs_full_pipeline_and_returns_result(
        self,
        extract_mock,
        map_mock,
        assess_mock,
        generate_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        mapping = build_mapping_result()
        report = build_extraction_report()
        output_path = ROOT / "tests" / "output" / "pipeline_from_files.docx"

        extract_mock.return_value = extraction_result
        map_mock.return_value = mapping
        assess_mock.return_value = report
        generate_mock.return_value = PipelineResult(
            context=mapping.context, output_path=output_path
        )

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": ""}):
            result = generate_memorial_eletrico_v1_from_ingested_files(ingested_files, output_path)

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.output_path, output_path)
        self.assertEqual(result.extraction_report, report)

    @patch("app.services.pipeline_from_files.generate_memorial_eletrico_v1")
    @patch("app.services.pipeline_from_files.assess_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_raises_validation_error_with_extraction_report(
        self,
        extract_mock,
        map_mock,
        assess_mock,
        generate_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        mapping = build_mapping_result()
        report = build_extraction_report()
        output_path = ROOT / "tests" / "output" / "pipeline_from_files_invalid.docx"

        extract_mock.return_value = build_extraction_result()
        map_mock.return_value = mapping
        assess_mock.return_value = report
        generate_mock.side_effect = MemorialValidationError(
            [ValidationIssue(path="$", message="'documento' is a required property", validator="required")]
        )

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": ""}):
            with self.assertRaises(MemorialValidationError) as ctx:
                generate_memorial_eletrico_v1_from_ingested_files(ingested_files, output_path)

        self.assertIsNotNone(ctx.exception.extraction_report)

    @patch("app.services.pipeline_from_files.generate_memorial_telecom_v1")
    @patch("app.services.pipeline_from_files.assess_telecom_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_telecom_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_runs_telecom_pipeline_and_returns_result(
        self,
        extract_mock,
        map_mock,
        assess_mock,
        generate_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        mapping = build_mapping_result()
        report = build_extraction_report()
        output_path = ROOT / "tests" / "output" / "pipeline_from_files_telecom.docx"

        extract_mock.return_value = extraction_result
        map_mock.return_value = mapping
        assess_mock.return_value = report
        generate_mock.return_value = PipelineResult(
            context=mapping.context, output_path=output_path
        )

        result = generate_memorial_telecom_v1_from_ingested_files(ingested_files, output_path)

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.output_path, output_path)
        self.assertEqual(result.extraction_report, report)

    @patch("app.services.pipeline_from_files.generate_memorial_telecom_v1")
    @patch("app.services.pipeline_from_files.assess_telecom_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_telecom_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_telecom_pipeline_raises_validation_error_with_extraction_report(
        self,
        extract_mock,
        map_mock,
        assess_mock,
        generate_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        mapping = build_mapping_result()
        report = build_extraction_report()
        output_path = ROOT / "tests" / "output" / "pipeline_from_files_invalid_telecom.docx"

        extract_mock.return_value = build_extraction_result()
        map_mock.return_value = mapping
        assess_mock.return_value = report
        generate_mock.side_effect = MemorialValidationError(
            [ValidationIssue(path="$.obra", message="'tipologia' is a required property", validator="required")]
        )

        with self.assertRaises(MemorialValidationError) as ctx:
            generate_memorial_telecom_v1_from_ingested_files(ingested_files, output_path)

        self.assertIsNotNone(ctx.exception.extraction_report)

    @patch("app.services.pipeline_from_files.generate_memorial_gas_natural_v1")
    @patch("app.services.pipeline_from_files.assess_gas_natural_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_gas_natural_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_runs_gas_natural_pipeline_and_returns_result(
        self,
        extract_mock,
        map_mock,
        assess_mock,
        generate_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        mapping = build_mapping_result()
        report = build_extraction_report()
        output_path = ROOT / "tests" / "output" / "pipeline_from_files_gas_natural.docx"

        extract_mock.return_value = extraction_result
        map_mock.return_value = mapping
        assess_mock.return_value = report
        generate_mock.return_value = PipelineResult(
            context=mapping.context, output_path=output_path
        )

        result = generate_memorial_gas_natural_v1_from_ingested_files(ingested_files, output_path)

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.output_path, output_path)
        self.assertEqual(result.extraction_report, report)

    @patch("app.services.pipeline_from_files.generate_memorial_gas_natural_v1")
    @patch("app.services.pipeline_from_files.assess_gas_natural_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_gas_natural_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_gas_natural_pipeline_raises_validation_error_with_extraction_report(
        self,
        extract_mock,
        map_mock,
        assess_mock,
        generate_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        mapping = build_mapping_result()
        report = build_extraction_report()
        output_path = ROOT / "tests" / "output" / "pipeline_from_files_invalid_gas_natural.docx"

        extract_mock.return_value = build_extraction_result()
        map_mock.return_value = mapping
        assess_mock.return_value = report
        generate_mock.side_effect = MemorialValidationError(
            [ValidationIssue(path="$.crm", message="'pavimento' is a required property", validator="required")]
        )

        with self.assertRaises(MemorialValidationError) as ctx:
            generate_memorial_gas_natural_v1_from_ingested_files(ingested_files, output_path)

        self.assertIsNotNone(ctx.exception.extraction_report)

    @patch("app.services.pipeline_from_files.generate_memorial_glp_v1")
    @patch("app.services.pipeline_from_files.assess_glp_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_glp_context")
    @patch("app.services.pipeline_from_files.extract_glp_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_runs_glp_pipeline_preserving_original_ramal_diameter(
        self,
        extract_mock,
        extract_llm_mock,
        map_mock,
        assess_mock,
        generate_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = build_extraction_result()
        report = build_extraction_report()
        output_path = ROOT / "tests" / "output" / "pipeline_from_files_glp.docx"

        extract_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context={
            "obra": {"construtora": "LLM GLP"},
            "abastecimento": {"qtd_tanques": 2, "pavimento": "terreo"},
            "dimensionamento": {"qtd_fogao": 56, "qtd_aquecedor": 0, "qtd_churrasqueira": 5},
            "soma": {"qtd_pontos_de_utilizacao": 61},
            "ramal": {"primario_diametro": '1 1/4"', "primario_material": "aco carbono", "primario_pavimento": "subsolo"},
            "numero": {"prancha": "05/05"},
            "teto_ou_piso": "teto",
        })
        map_mock.return_value = build_mapping_result()
        assess_mock.return_value = report
        generate_mock.return_value = PipelineResult(
            context={},
            output_path=output_path,
        )

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            generate_memorial_glp_v1_from_ingested_files(ingested_files, output_path)

        called_context = generate_mock.call_args.args[0]
        self.assertEqual(called_context["ramal"]["primario_diametro"], '1 1/4"')


class GenerateFromUploadedFilesTests(unittest.IsolatedAsyncioTestCase):
    @patch("app.services.pipeline_from_files.generate_memorial_eletrico_v1_from_ingested_files")
    @patch("app.services.pipeline_from_files.ingest_uploaded_files", new_callable=AsyncMock)
    async def test_calls_ingestion_and_pipeline(self, ingest_mock, pipeline_mock) -> None:
        upload_files = [
            UploadFile(
                filename="projeto.docx",
                file=io.BytesIO(b"PK\x03\x04docx"),
                headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
            )
        ]
        ingested_files = [build_ingested_file()]
        ingestion_result = FileIngestionResult(
            request_dir="/tmp/eletrico_v1_upload_123",
            files=ingested_files,
        )
        output_path = ROOT / "tests" / "output" / "pipeline_from_uploaded_files.docx"
        expected_result = PipelineResult(context={"obra": {}}, output_path=output_path)

        ingest_mock.return_value = ingestion_result
        pipeline_mock.return_value = expected_result

        result = await generate_memorial_eletrico_v1_from_uploaded_files(upload_files, output_path)

        self.assertEqual(result, expected_result)
        ingest_mock.assert_awaited_once_with(upload_files)
        pipeline_mock.assert_called_once_with(ingested_files, output_path)

    @patch("app.services.pipeline_from_files.cleanup_ingestion_result")
    @patch("app.services.pipeline_from_files.generate_memorial_eletrico_v1_from_ingested_files")
    @patch("app.services.pipeline_from_files.ingest_uploaded_files", new_callable=AsyncMock)
    async def test_cleanup_runs_even_on_error(
        self, ingest_mock, pipeline_mock, cleanup_mock
    ) -> None:
        upload_files = [
            UploadFile(
                filename="projeto.docx",
                file=io.BytesIO(b"PK\x03\x04docx"),
                headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
            )
        ]
        ingestion_result = FileIngestionResult(
            request_dir=mkdtemp(prefix="eletrico_v1_upload_test_"),
            files=[build_ingested_file()],
        )
        output_path = ROOT / "tests" / "output" / "pipeline_from_uploaded_files_invalid.docx"
        ingest_mock.return_value = ingestion_result
        pipeline_mock.side_effect = MemorialValidationError(
            [ValidationIssue(path="$", message="'documento' is a required property", validator="required")]
        )

        with self.assertRaises(MemorialValidationError):
            await generate_memorial_eletrico_v1_from_uploaded_files(upload_files, output_path)

        cleanup_mock.assert_called_once_with(ingestion_result)

    @patch("app.services.pipeline_from_files.generate_memorial_telecom_v1_from_ingested_files")
    @patch("app.services.pipeline_from_files.ingest_uploaded_files", new_callable=AsyncMock)
    async def test_calls_ingestion_and_telecom_pipeline(self, ingest_mock, pipeline_mock) -> None:
        upload_files = [
            UploadFile(
                filename="projeto.docx",
                file=io.BytesIO(b"PK\x03\x04docx"),
                headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
            )
        ]
        ingested_files = [build_ingested_file()]
        ingestion_result = FileIngestionResult(
            request_dir="/tmp/telecom_v1_upload_123",
            files=ingested_files,
        )
        output_path = ROOT / "tests" / "output" / "pipeline_from_uploaded_files_telecom.docx"
        expected_result = PipelineResult(context={"obra": {}}, output_path=output_path)

        ingest_mock.return_value = ingestion_result
        pipeline_mock.return_value = expected_result

        result = await generate_memorial_telecom_v1_from_uploaded_files(upload_files, output_path)

        self.assertEqual(result, expected_result)
        ingest_mock.assert_awaited_once_with(upload_files)
        pipeline_mock.assert_called_once_with(ingested_files, output_path)

    @patch("app.services.pipeline_from_files.cleanup_ingestion_result")
    @patch("app.services.pipeline_from_files.generate_memorial_telecom_v1_from_ingested_files")
    @patch("app.services.pipeline_from_files.ingest_uploaded_files", new_callable=AsyncMock)
    async def test_telecom_cleanup_runs_even_on_error(
        self, ingest_mock, pipeline_mock, cleanup_mock
    ) -> None:
        upload_files = [
            UploadFile(
                filename="projeto.docx",
                file=io.BytesIO(b"PK\x03\x04docx"),
                headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
            )
        ]
        ingestion_result = FileIngestionResult(
            request_dir=mkdtemp(prefix="telecom_v1_upload_test_"),
            files=[build_ingested_file()],
        )
        output_path = ROOT / "tests" / "output" / "pipeline_from_uploaded_files_invalid_telecom.docx"
        ingest_mock.return_value = ingestion_result
        pipeline_mock.side_effect = MemorialValidationError(
            [ValidationIssue(path="$", message="'documento' is a required property", validator="required")]
        )

        with self.assertRaises(MemorialValidationError):
            await generate_memorial_telecom_v1_from_uploaded_files(upload_files, output_path)

        cleanup_mock.assert_called_once_with(ingestion_result)

    @patch("app.services.pipeline_from_files.generate_memorial_gas_natural_v1_from_ingested_files")
    @patch("app.services.pipeline_from_files.ingest_uploaded_files", new_callable=AsyncMock)
    async def test_calls_ingestion_and_gas_natural_pipeline(self, ingest_mock, pipeline_mock) -> None:
        upload_files = [
            UploadFile(
                filename="projeto.docx",
                file=io.BytesIO(b"PK\x03\x04docx"),
                headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
            )
        ]
        ingested_files = [build_ingested_file()]
        ingestion_result = FileIngestionResult(
            request_dir="/tmp/gas_natural_v1_upload_123",
            files=ingested_files,
        )
        output_path = ROOT / "tests" / "output" / "pipeline_from_uploaded_files_gas_natural.docx"
        expected_result = PipelineResult(context={"obra": {}}, output_path=output_path)

        ingest_mock.return_value = ingestion_result
        pipeline_mock.return_value = expected_result

        result = await generate_memorial_gas_natural_v1_from_uploaded_files(upload_files, output_path)

        self.assertEqual(result, expected_result)
        ingest_mock.assert_awaited_once_with(upload_files)
        pipeline_mock.assert_called_once_with(ingested_files, output_path)

    @patch("app.services.pipeline_from_files.cleanup_ingestion_result")
    @patch("app.services.pipeline_from_files.generate_memorial_gas_natural_v1_from_ingested_files")
    @patch("app.services.pipeline_from_files.ingest_uploaded_files", new_callable=AsyncMock)
    async def test_gas_natural_cleanup_runs_even_on_error(
        self, ingest_mock, pipeline_mock, cleanup_mock
    ) -> None:
        upload_files = [
            UploadFile(
                filename="projeto.docx",
                file=io.BytesIO(b"PK\x03\x04docx"),
                headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
            )
        ]
        ingestion_result = FileIngestionResult(
            request_dir=mkdtemp(prefix="gas_natural_v1_upload_test_"),
            files=[build_ingested_file()],
        )
        output_path = ROOT / "tests" / "output" / "pipeline_from_uploaded_files_invalid_gas_natural.docx"
        ingest_mock.return_value = ingestion_result
        pipeline_mock.side_effect = MemorialValidationError(
            [ValidationIssue(path="$", message="'documento' is a required property", validator="required")]
        )

        with self.assertRaises(MemorialValidationError):
            await generate_memorial_gas_natural_v1_from_uploaded_files(upload_files, output_path)

        cleanup_mock.assert_called_once_with(ingestion_result)


class TelecomMappingFromFilesTests(unittest.TestCase):
    @patch("app.services.pipeline_from_files.assess_telecom_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_telecom_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_extract_telecom_mapping_from_ingested_files(
        self,
        extract_mock,
        map_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        mapping = build_mapping_result()
        report = build_extraction_report()

        extract_mock.return_value = build_extraction_result()
        map_mock.return_value = mapping
        assess_mock.return_value = report

        result_mapping, result_report = extract_telecom_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping, mapping)
        self.assertEqual(result_report, report)
        extract_mock.assert_called_once_with(ingested_files)
        map_mock.assert_called_once()
        assess_mock.assert_called_once()


class GasNaturalMappingFromFilesTests(unittest.TestCase):
    @patch("app.services.pipeline_from_files.assess_gas_natural_extraction_coverage")
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_gas_natural_context")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_extract_gas_natural_mapping_from_ingested_files(
        self,
        extract_mock,
        map_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        mapping = build_mapping_result()
        report = build_extraction_report()

        extract_mock.return_value = build_extraction_result()
        map_mock.return_value = mapping
        assess_mock.return_value = report

        result_mapping, result_report = extract_gas_natural_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping, mapping)
        self.assertEqual(result_report, report)
        extract_mock.assert_called_once_with(ingested_files)
        map_mock.assert_called_once()
        assess_mock.assert_called_once()


class FillGapsTests(unittest.TestCase):
    def test_fills_none_fields_from_supplement(self) -> None:
        base = {"obra": {"construtora": "Alpha", "nome": None}}
        supplement = {"obra": {"construtora": "Beta", "nome": "Edifício X"}}

        filled = _fill_gaps(base, supplement)

        self.assertEqual(filled, {"obra": {"nome": "Edifício X"}})

    def test_does_not_overwrite_existing_values(self) -> None:
        base = {"obra": {"construtora": "Alpha"}}
        supplement = {"obra": {"construtora": "Beta"}}

        filled = _fill_gaps(base, supplement)

        self.assertEqual(filled, {})

    def test_fills_missing_section(self) -> None:
        base = {"obra": {"construtora": "Alpha"}}
        supplement = {"energia": {"tem_subestacao": True}}

        filled = _fill_gaps(base, supplement)

        self.assertEqual(filled, {"energia": {"tem_subestacao": True}})

    def test_ignores_non_dict_sections(self) -> None:
        base = {"obra": {"construtora": "Alpha"}}
        supplement = {"observacoes": "nota", "obra": {"nome": "Ed"}}

        filled = _fill_gaps(base, supplement)

        self.assertEqual(filled, {"obra": {"nome": "Ed"}})

    def test_empty_supplement_returns_empty(self) -> None:
        self.assertEqual(_fill_gaps({"obra": {"construtora": "A"}}, {}), {})

    def test_supplement_null_values_not_applied(self) -> None:
        base = {"obra": {"construtora": None}}
        supplement = {"obra": {"construtora": None}}

        filled = _fill_gaps(base, supplement)

        self.assertEqual(filled, {})


if __name__ == "__main__":
    unittest.main()
