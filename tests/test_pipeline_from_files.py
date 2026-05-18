from __future__ import annotations

import io
import json
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
    _assemble_glp_v2_payload,
    _build_extraction_report_payload,
    _normalize_gas_natural_context,
    _normalize_glp_context,
    _fill_gaps,
    extract_mapping_from_ingested_files,
    extract_glp_v2_mapping_from_ingested_files,
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
from app.services.quantitative_extraction import (
    QuantitativeCandidate,
    resolve_glp_v2_quantitatives,
)


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


def build_glp_v2_quantitative_extraction_result() -> ProjectExtractionResult:
    tipo = """
    QUADRO DE QUANTITATIVO MEDIÇÃO
    1º AO 7º PAVIMENTO - (07 PAV X 04 APTOS [02 PONTOS] = 56 PONTOS)
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    0.60 Fogão 0,30 Churrasqueira
    """
    pavimentos_superiores = """
    7º E 8º PAVIMENTO
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    """
    terreo = """
    TÉRREO
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    Fogão 7.000 Kcal/h Churrasqueira 7.000 Kcal/h
    """
    return ProjectExtractionResult(
        raw_text="\n".join([tipo, pavimentos_superiores, terreo]),
        source_files=[
            ExtractedSourceFile(
                original_filename="03_tipo.pdf",
                stored_filename="03_tipo.pdf",
                extension=".pdf",
                saved_path="/tmp/03_tipo.pdf",
                extracted_text=tipo,
            ),
            ExtractedSourceFile(
                original_filename="04_7_e_8_pavimento.pdf",
                stored_filename="04_7_e_8_pavimento.pdf",
                extension=".pdf",
                saved_path="/tmp/04_7_e_8_pavimento.pdf",
                extracted_text=pavimentos_superiores,
            ),
            ExtractedSourceFile(
                original_filename="02_terreo.pdf",
                stored_filename="02_terreo.pdf",
                extension=".pdf",
                saved_path="/tmp/02_terreo.pdf",
                extracted_text=terreo,
            ),
        ],
        signals={"total_files": 3},
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
                "batch_merge_fallback_used": True,
                "batch_merge_errors": [
                    {
                        "batch_index": 0,
                        "error_type": "TimeoutError",
                        "files": ["a.pdf", "b.pdf"],
                    }
                ],
            },
        )

        payload = _build_extraction_report_payload(
            report,
            conflicts=[{"type": "glp_total_points_conflict"}],
        )

        self.assertEqual(payload["cross_validation"]["batch_size"], 5)
        self.assertTrue(payload["cross_validation"]["fallback_used"])
        self.assertTrue(payload["cross_validation"]["batch_merge_fallback_used"])
        self.assertEqual(
            payload["cross_validation"]["batch_merge_errors"][0]["error_type"],
            "TimeoutError",
        )
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

    @patch("app.services.pipeline_from_files.assess_extraction_coverage")
    @patch("app.services.pipeline_from_files.extract_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_eletrico_mapper_corrects_generator_false_positive_from_legend(
        self,
        extract_files_mock,
        extract_llm_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = ProjectExtractionResult(
            raw_text="Legenda: simbolo de gerador conforme ABNT, sem painel de gerador instalado.",
            source_files=[],
            signals={"total_files": 1},
        )
        llm_context = {
            "gerador": {
                "tem_gerador": True,
                "qtd": 1,
                "potencia_kva": 250,
                "tipo_atendimento": "condominio",
            }
        }

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        assess_mock.return_value = build_extraction_report()

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, report = extract_mapping_from_ingested_files(ingested_files)

        self.assertEqual(
            result_mapping.context["gerador"],
            {
                "tem_gerador": False,
                "qtd": 0,
                "potencia_kva": 0,
                "tipo_atendimento": "condominio",
            },
        )
        self.assertEqual(
            report.cross_validation["quantitative_resolutions"][0]["field_path"],
            "gerador.tem_gerador",
        )

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
    def test_gas_natural_reconciles_authoritative_quantitative_mapper_values(
        self,
        extract_files_mock,
        extract_llm_mock,
        assess_mock,
    ) -> None:
        ingested_files = [build_ingested_file()]
        extraction_result = ProjectExtractionResult(
            raw_text=(
                "PROJETO DE INSTALAÇÕES DE GÁS NATURAL\n"
                "FOGÃO: 4\n"
                "0 aquecedores\n"
                "CHURRASQUEIRA: 1\n"
                "( 1 PAVIMENTO = 5 PONTOS )\n"
            ),
            source_files=[],
            signals={"total_files": 1},
        )
        llm_context = {
            "obra": {"construtora": "LLM Gas"},
            "dimensionamento": {
                "qtd_fogao": 3,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 1,
            },
            "soma": {"qtd_pontos_de_utilizacao": 999},
        }

        extract_files_mock.return_value = extraction_result
        extract_llm_mock.return_value = LLMExtractionRunResult(context=llm_context)
        assess_mock.return_value = build_extraction_report()

        with patch.dict(os.environ, {"USE_LLM_EXTRACTION": "true"}):
            result_mapping, report = extract_gas_natural_mapping_from_ingested_files(ingested_files)

        self.assertEqual(result_mapping.context["dimensionamento"]["qtd_fogao"], 4)
        self.assertEqual(result_mapping.context["dimensionamento"]["qtd_aquecedor"], 0)
        self.assertEqual(result_mapping.context["dimensionamento"]["qtd_churrasqueira"], 1)
        self.assertEqual(result_mapping.context["soma"]["qtd_pontos_de_utilizacao"], 5)
        self.assertEqual(
            {
                item["field_path"]
                for item in report.cross_validation["quantitative_resolutions"]
            },
            {
                "dimensionamento.qtd_fogao",
                "soma.qtd_pontos_de_utilizacao",
            },
        )

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
            "abastecimento": {"qtd_tanques": 1, "pavimento": "terreo"},
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


class GlpV2AssemblyTests(unittest.TestCase):
    """MAKAI-style regression shape: 1 tank, 29 apts, 35+35 points, 1 1/4\" pipe (no project name hardcoding)."""

    def test_quantitative_resolver_prefers_authoritative_point_candidates(self) -> None:
        merged = {
            "obra": {"qtd_apartamentos": 29},
            "dimensionamento": {
                "qtd_fogao": 28,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 28,
                "qtd_outros": 0,
            },
            "pontos_utilizacao": {
                "fogao": 28,
                "churrasqueira": 28,
                "total_extraido": 61,
            },
        }
        authoritative_candidates = [
            QuantitativeCandidate(
                field_path="pontos_utilizacao.fogao",
                value=35,
                unit="un",
                entity="fogao",
                memorial_type="glp_v2",
                source_file="corte.pdf",
                page_number=1,
                source_kind="installed_quantity_table",
                extraction_method="deterministic_visual_evidence",
                evidence_text="35 pontos de fogão instalados",
                confidence="high",
            ),
            QuantitativeCandidate(
                field_path="pontos_utilizacao.churrasqueira",
                value=35,
                unit="un",
                entity="churrasqueira",
                memorial_type="glp_v2",
                source_file="corte.pdf",
                page_number=1,
                source_kind="installed_quantity_table",
                extraction_method="deterministic_visual_evidence",
                evidence_text="35 pontos de churrasqueira instalados",
                confidence="high",
            ),
        ]

        result = resolve_glp_v2_quantitatives(
            merged,
            [],
            extra_candidates=authoritative_candidates,
        )

        self.assertEqual(result.dimensionamento["qtd_fogao"], 35)
        self.assertEqual(result.dimensionamento["qtd_churrasqueira"], 35)
        self.assertEqual(result.pontos_utilizacao["total_calculado"], 70)
        self.assertFalse(
            [conflict for conflict in result.conflicts if conflict.get("status") == "unresolved"]
        )
        self.assertEqual(
            result.conflicts[0]["resolucao"],
            "glp_v2_authoritative_individual_points",
        )

    def test_quantitative_resolver_returns_auditable_resolution_for_even_total_split(self) -> None:
        merged = {
            "obra": {"qtd_apartamentos": 29},
            "dimensionamento": {
                "qtd_fogao": 30,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 4,
                "qtd_outros": 0,
            },
            "pontos_utilizacao": {
                "fogao": 30,
                "churrasqueira": 4,
                "total_extraido": 70,
            },
        }

        result = resolve_glp_v2_quantitatives(merged, [])

        self.assertEqual(result.dimensionamento["qtd_fogao"], 35)
        self.assertEqual(result.dimensionamento["qtd_churrasqueira"], 35)
        self.assertEqual(result.pontos_utilizacao["total_calculado"], 70)
        self.assertEqual(result.conflicts[0]["status"], "resolved")
        self.assertEqual(result.conflicts[0]["tipo"], "glp_v2_points_total_mismatch")
        point_resolution = next(
            item for item in result.resolutions
            if item["rule"] == "glp_v2_even_total_split"
        )
        self.assertEqual(point_resolution["field_path"], "pontos_utilizacao.total_calculado")
        self.assertGreaterEqual(len(point_resolution["candidates"]), 3)

    def test_assemble_drops_mapper_apartment_proxy_conflict_when_final_points_differ(self) -> None:
        merged = {
            "obra": {
                "numero_cadastro": "X",
                "construtora": "C",
                "nome": "N",
                "localizacao": "L",
                "tipo_edificacao": "residencial",
                "tipologia": "torre",
                "qtd_apartamentos": 29,
                "qtd_lojas": 0,
                "qtd_restaurantes": 0,
            },
            "tanques": {"quantidade": 1},
            "abastecimento": {"pavimento": "térreo"},
            "dimensionamento": {
                "qtd_fogao": 35,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 35,
                "qtd_outros": 0,
            },
            "pontos_utilizacao": {"total_extraido": 70},
            "ramal": {
                "primario_diametro": '1 1/4"',
                "primario_material": "aço carbono",
                "primario_pavimento": "térreo",
            },
            "numero": {"prancha": "01/04"},
            "teto_ou_piso": "piso",
        }
        mapper_conflict = {
            "tipo": "glp_v2_fogao_apartamentos_colision",
            "status": "unresolved",
            "valores_observados": [29],
            "fontes": ["glp_fogao_count_regex", "qtd_apartamentos"],
        }

        out = _assemble_glp_v2_payload(merged, [mapper_conflict])

        self.assertEqual(out["pontos_utilizacao"]["fogao"], 35)
        self.assertEqual(out["obra"]["qtd_apartamentos"]["valor"], 29)
        self.assertEqual(out["pontos_utilizacao"]["conflitos"], [])

    def test_assemble_resolves_even_total_mismatch_for_fogao_and_churrasqueira_only(self) -> None:
        merged = {
            "obra": {
                "numero_cadastro": "X",
                "construtora": "C",
                "nome": "N",
                "localizacao": "L",
                "tipo_edificacao": "residencial",
                "tipologia": "torre",
                "qtd_apartamentos": 29,
                "qtd_lojas": 0,
                "qtd_restaurantes": 0,
            },
            "tanques": {"quantidade": 1},
            "abastecimento": {"pavimento": "térreo"},
            "dimensionamento": {
                "qtd_fogao": 30,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 4,
                "qtd_outros": 0,
            },
            "pontos_utilizacao": {
                "fogao": 30,
                "churrasqueira": 4,
                "total_extraido": 70,
            },
            "ramal": {
                "primario_diametro": '1 1/4"',
                "primario_material": "aço carbono",
                "primario_pavimento": "térreo",
            },
            "numero": {"prancha": "01/04"},
            "teto_ou_piso": "piso",
        }

        out = _assemble_glp_v2_payload(merged, [])

        self.assertEqual(out["pontos_utilizacao"]["fogao"], 35)
        self.assertEqual(out["pontos_utilizacao"]["churrasqueira"], 35)
        self.assertEqual(out["pontos_utilizacao"]["total_calculado"], 70)
        self.assertEqual(
            out["pontos_utilizacao"]["conflitos"][0]["status"],
            "resolved",
        )
        self.assertEqual(
            out["pontos_utilizacao"]["conflitos"][0]["resolucao"],
            "glp_v2_even_total_split",
        )

    def test_assemble_keeps_unresolved_total_mismatch_when_even_split_is_not_safe(self) -> None:
        merged = {
            "obra": {
                "numero_cadastro": "X",
                "construtora": "C",
                "nome": "N",
                "localizacao": "L",
                "tipo_edificacao": "residencial",
                "tipologia": "torre",
                "qtd_apartamentos": 29,
                "qtd_lojas": 0,
                "qtd_restaurantes": 0,
            },
            "tanques": {"quantidade": 1},
            "abastecimento": {"pavimento": "térreo"},
            "dimensionamento": {
                "qtd_fogao": 30,
                "qtd_aquecedor": 1,
                "qtd_churrasqueira": 4,
                "qtd_outros": 0,
            },
            "pontos_utilizacao": {
                "fogao": 30,
                "churrasqueira": 4,
                "aquecedor": 1,
                "total_extraido": 70,
            },
            "ramal": {
                "primario_diametro": '1 1/4"',
                "primario_material": "aço carbono",
                "primario_pavimento": "térreo",
            },
            "numero": {"prancha": "01/04"},
            "teto_ou_piso": "piso",
        }

        out = _assemble_glp_v2_payload(merged, [])

        self.assertEqual(out["pontos_utilizacao"]["total_calculado"], 35)
        self.assertEqual(
            out["pontos_utilizacao"]["conflitos"][0]["status"],
            "unresolved",
        )

    def test_assemble_matches_expected_fixture_subset(self) -> None:
        merged = {
            "obra": {
                "numero_cadastro": "X",
                "construtora": "C",
                "nome": "N",
                "localizacao": "L",
                "tipo_edificacao": "residencial",
                "tipologia": "torre",
                "qtd_apartamentos": 29,
                "qtd_lojas": 0,
                "qtd_restaurantes": 0,
            },
            "tanques": {"quantidade": 1, "tipo": "P-190"},
            "abastecimento": {"pavimento": "térreo"},
            "dimensionamento": {
                "qtd_fogao": 35,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 35,
                "qtd_outros": 0,
            },
            "pontos_utilizacao": {"total_extraido": 70},
            "ramal": {
                "primario_diametro": '1 1/4"',
                "primario_material": "aço carbono",
                "primario_pavimento": "térreo",
            },
            "numero": {"prancha": "01/04"},
            "teto_ou_piso": "piso",
        }
        out = _assemble_glp_v2_payload(merged, [])
        fixture_path = ROOT / "tests" / "fixtures" / "glp_v2_makai_expected.json"
        with fixture_path.open("r", encoding="utf-8") as f:
            expected = json.load(f)
        self.assertEqual(out["tanques"]["quantidade"], expected["tanques"]["quantidade"])
        self.assertEqual(out["obra"]["qtd_apartamentos"]["valor"], expected["obra"]["qtd_apartamentos"]["valor"])
        self.assertEqual(out["dimensionamento"]["qtd_fogao"], expected["dimensionamento"]["qtd_fogao"])
        self.assertEqual(out["dimensionamento"]["qtd_churrasqueira"], expected["dimensionamento"]["qtd_churrasqueira"])
        self.assertEqual(out["pontos_utilizacao"]["total_calculado"], expected["pontos_utilizacao"]["total_calculado"])
        self.assertEqual(
            out["diametros"]["tubulacao_principal"]["valor_formatado"],
            expected["diametros"]["tubulacao_principal"]["valor_formatado"],
        )
        self.assertTrue(out["diametros"]["valvula_esfera"].get("inferido"))

    @patch("app.services.pipeline_from_files.is_llm_extraction_enabled", return_value=True)
    @patch("app.services.pipeline_from_files.map_extraction_to_partial_glp_v2_context")
    @patch("app.services.pipeline_from_files.extract_glp_v2_with_llm_result")
    @patch("app.services.pipeline_from_files.extract_project_files")
    def test_glp_v2_extraction_report_includes_quantitative_resolutions(
        self,
        extract_project_mock,
        llm_mock,
        mapper_mock,
        _enabled_mock,
    ) -> None:
        merged = {
            "obra": {
                "numero_cadastro": "X",
                "construtora": "C",
                "nome": "N",
                "localizacao": "L",
                "tipo_edificacao": "residencial",
                "tipologia": "torre",
                "qtd_apartamentos": 29,
                "qtd_lojas": 0,
                "qtd_restaurantes": 0,
            },
            "tanques": {"quantidade": 1},
            "abastecimento": {"pavimento": "térreo"},
            "dimensionamento": {
                "qtd_fogao": 28,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 28,
                "qtd_outros": 0,
            },
            "pontos_utilizacao": {
                "fogao": 28,
                "churrasqueira": 28,
                "total_extraido": 61,
            },
            "ramal": {
                "primario_diametro": '1 1/4"',
                "primario_material": "aço carbono",
                "primario_pavimento": "térreo",
            },
            "numero": {"prancha": "01/04"},
            "teto_ou_piso": "piso",
        }
        extract_project_mock.return_value = build_glp_v2_quantitative_extraction_result()
        llm_mock.return_value = LLMExtractionRunResult(
            context=merged,
            cross_validation={"batch_count": 1},
        )
        mapper_mock.return_value = MappingResult(context={}, evidence={})

        mapping, report = extract_glp_v2_mapping_from_ingested_files([build_ingested_file()])

        self.assertEqual(mapping.context["pontos_utilizacao"]["fogao"], 35)
        self.assertEqual(mapping.context["pontos_utilizacao"]["churrasqueira"], 35)
        self.assertIsNotNone(report.cross_validation)
        quantitative = report.cross_validation["quantitative_resolutions"]
        point_resolution = next(
            item for item in quantitative
            if item["rule"] == "glp_v2_authoritative_individual_points"
        )
        self.assertEqual(point_resolution["selected_value"], 70)


if __name__ == "__main__":
    unittest.main()
