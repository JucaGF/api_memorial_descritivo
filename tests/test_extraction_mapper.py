from __future__ import annotations

import unittest

from app.services.extraction_mapper import (
    ExtractionReport,
    FieldExtraction,
    MappingResult,
    assess_extraction_coverage,
    map_extraction_to_partial_context,
)
from app.services.project_extractor import ExtractedSourceFile, ProjectExtractionResult


def build_extraction_result(raw_text: str) -> ProjectExtractionResult:
    return ProjectExtractionResult(
        raw_text=raw_text,
        source_files=[
            ExtractedSourceFile(
                original_filename="projeto.pdf",
                stored_filename="01_projeto.pdf",
                extension=".pdf",
                saved_path="/tmp/01_projeto.pdf",
                extracted_text=raw_text,
            )
        ],
        signals={
            "total_files": 1,
            "file_types": [".pdf"],
            "has_pdf": True,
            "has_docx": False,
            "total_characters": len(raw_text),
        },
    )


# ── texto no formato carimbo real (sem rótulos) ───────────────────────────────

CARIMBO_TEXT = """
E-6.0
23/2024
MAKAI
MGA CONSTRUÇÕES E INCORPORAÇÕES LTDA
AV. MAX ZAGEL, LT 05A, QD 12, LOTEAMENTO JARDIM ATLÂNTICO - CABEDELO - PB
MGA MAKAI - PROJETO DE INSTALAÇÕES ELÉTRICAS
"""

# ── texto no formato rotulado (fallback) ─────────────────────────────────────

LABELED_TEXT = """
CONSTRUTORA: MGA Construções e Incorporações LTDA
NOME DA OBRA: Edifício Makai
LOCALIZAÇÃO: Avenida Max Zagel, Cabedelo - PB
Alimentação em média tensão 15 kV.
Subestação abrigada abaixadora com medição em MT.
Sistema de aterramento TN-S.
Seção do cabo de média tensão: 35 mm².
"""


class MappingResultStructureTests(unittest.TestCase):
    def test_returns_mapping_result(self) -> None:
        result = map_extraction_to_partial_context(build_extraction_result(CARIMBO_TEXT))

        self.assertIsInstance(result, MappingResult)
        self.assertIsInstance(result.context, dict)
        self.assertIsInstance(result.evidence, dict)

    def test_filled_fields_have_field_extraction_in_evidence(self) -> None:
        result = map_extraction_to_partial_context(build_extraction_result(CARIMBO_TEXT))

        for path, extraction in result.evidence.items():
            self.assertIsInstance(extraction, FieldExtraction)
            self.assertIsNotNone(extraction.value)
            self.assertIsNotNone(extraction.rule)
            self.assertIn(extraction.confidence, ("high", "medium", "low"))

    def test_context_is_sparse_missing_fields_are_absent(self) -> None:
        raw_text = "Planta baixa do pavimento tipo."
        result = map_extraction_to_partial_context(build_extraction_result(raw_text))

        self.assertNotIn("construtora", result.context.get("obra", {}))
        self.assertNotIn("nome", result.context.get("obra", {}))
        self.assertNotIn("tipo_sistema", result.context.get("aterramento", {}))


class CarimboExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = map_extraction_to_partial_context(build_extraction_result(CARIMBO_TEXT))
        self.context = self.result.context

    def test_extracts_construtora_from_carimbo(self) -> None:
        self.assertEqual(
            self.context["obra"]["construtora"],
            "MGA CONSTRUÇÕES E INCORPORAÇÕES LTDA",
        )

    def test_extracts_nome_from_line_before_construtora(self) -> None:
        self.assertEqual(self.context["obra"]["nome"], "MAKAI")

    def test_extracts_localizacao_from_line_after_construtora(self) -> None:
        self.assertIn("MAX ZAGEL", self.context["obra"]["localizacao"])
        self.assertIn("CABEDELO", self.context["obra"]["localizacao"])

    def test_carimbo_fields_have_high_confidence(self) -> None:
        self.assertEqual(self.result.evidence["obra.construtora"].confidence, "high")
        self.assertEqual(self.result.evidence["obra.nome"].confidence, "high")
        self.assertEqual(self.result.evidence["obra.localizacao"].confidence, "high")


class LabeledFallbackExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = map_extraction_to_partial_context(
            build_extraction_result(LABELED_TEXT)
        ).context

    def test_extracts_construtora_from_labeled_line(self) -> None:
        self.assertEqual(
            self.context["obra"]["construtora"],
            "MGA Construções e Incorporações LTDA",
        )

    def test_extracts_localizacao_from_label(self) -> None:
        self.assertEqual(
            self.context["obra"]["localizacao"],
            "Avenida Max Zagel, Cabedelo - PB",
        )

    def test_detects_subestacao_true(self) -> None:
        self.assertTrue(self.context["energia"]["tem_subestacao"])

    def test_extracts_aterramento_tipo_sistema(self) -> None:
        self.assertEqual(self.context["aterramento"]["tipo_sistema"], "TN-S")

    def test_extracts_mt_tensao_kv(self) -> None:
        self.assertEqual(self.context["mt"]["tensao_kv"], 15)

    def test_extracts_mt_secao_cabo_mm2(self) -> None:
        self.assertEqual(self.context["mt"]["secao_cabo_mm2"], 35)


class SubestacaoDetectionTests(unittest.TestCase):
    def test_detects_sem_subestacao(self) -> None:
        raw_text = "O projeto não possui subestação e será alimentado em baixa tensão."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertFalse(context["energia"]["tem_subestacao"])
        self.assertNotIn("tipo_subestacao", context.get("energia", {}))

    def test_detects_subestacao_present(self) -> None:
        raw_text = "A subestação abrigada será instalada no térreo."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertTrue(context["energia"]["tem_subestacao"])


class NaoInclusosCircuitDetectionTests(unittest.TestCase):
    def test_sistema_com_circuito_incendio_marcado_como_incluido(self) -> None:
        raw_text = "Q.INCENDIO: sistema de alarme de incêndio integrado."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertFalse(context["nao_inclusos"]["alarme_incendio"])

    def test_sistema_sem_circuito_cftv_marcado_como_nao_incluso(self) -> None:
        raw_text = "Quadro geral de baixa tensão Q.GBT. Sistema elétrico residencial."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertTrue(context["nao_inclusos"]["cftv"])

    def test_circuito_cftv_encontrado_marcado_como_incluido(self) -> None:
        raw_text = "Q-CFTV: sistema de monitoramento instalado no pavimento térreo."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertFalse(context["nao_inclusos"]["cftv"])

    def test_todos_os_campos_nao_inclusos_sempre_presentes(self) -> None:
        raw_text = "Texto genérico sem menção a sistemas especializados."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        for field in ("cpct", "cftv", "alarme_patrimonial", "sonorizacao", "alarme_incendio", "automacao"):
            self.assertIn(field, context["nao_inclusos"])

    def test_ausencia_tem_confianca_baixa(self) -> None:
        raw_text = "Texto sem circuitos especializados."
        result = map_extraction_to_partial_context(build_extraction_result(raw_text))

        self.assertEqual(result.evidence["nao_inclusos.cftv"].confidence, "low")

    def test_presenca_tem_confianca_media(self) -> None:
        raw_text = "Q-CFTV instalado no pavimento térreo."
        result = map_extraction_to_partial_context(build_extraction_result(raw_text))

        self.assertEqual(result.evidence["nao_inclusos.cftv"].confidence, "medium")


class NewExtractorsTests(unittest.TestCase):
    def test_extracts_qtd_hastes(self) -> None:
        raw_text = "Sistema de aterramento com 3 hastes de aterramento cravadas."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertEqual(context["aterramento"]["qtd_hastes"], 3)

    def test_extracts_qtd_hastes_ordem_inversa(self) -> None:
        raw_text = "Aterramento composto por 2 hastes."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertEqual(context["aterramento"]["qtd_hastes"], 2)

    def test_extracts_perfilado_tipo(self) -> None:
        raw_text = "Instalação em perfilado tipo U de aço galvanizado."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertEqual(context["instalacao"]["perfilado_tipo"], "U")

    def test_extracts_qtd_apartamentos(self) -> None:
        raw_text = "Edifício residencial com 16 apartamentos por pavimento tipo."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertEqual(context["obra"]["qtd_apartamentos"], 16)

    def test_extracts_qtd_apartamentos_abbreviation(self) -> None:
        raw_text = "Total de 24 aptos distribuídos em 8 pavimentos."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertEqual(context["obra"]["qtd_apartamentos"], 24)

    def test_extracts_secao_cabo_cobre_mm2(self) -> None:
        raw_text = "Malha de aterramento em cabo de cobre 50mm²."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertEqual(context["aterramento"]["secao_cabo_cobre_mm2"], 50)

    def test_extracts_numero_cadastro(self) -> None:
        raw_text = "Projeto Nº: 23/2024\nResponsável técnico: Engª Andrea Dias"
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertEqual(context["obra"]["numero_cadastro"], "23/2024")

    def test_extracts_gerador_tipo_atendimento_condominio(self) -> None:
        raw_text = "Q-GERADOR: alimenta áreas comuns e iluminação de emergência."
        context = map_extraction_to_partial_context(build_extraction_result(raw_text)).context

        self.assertEqual(context["gerador"]["tipo_atendimento"], "condominio")


class AssessExtractionCoverageTests(unittest.TestCase):
    def test_filled_contains_extracted_fields(self) -> None:
        result = map_extraction_to_partial_context(build_extraction_result(CARIMBO_TEXT))
        report = assess_extraction_coverage(result)

        self.assertIsInstance(report, ExtractionReport)
        self.assertIn("obra.construtora", report.filled)
        self.assertIn("obra.nome", report.filled)
        self.assertIn("obra.localizacao", report.filled)

    def test_missing_contains_unextracted_fields(self) -> None:
        raw_text = "Texto genérico sem informações úteis para o memorial."
        result = map_extraction_to_partial_context(build_extraction_result(raw_text))
        report = assess_extraction_coverage(result)

        self.assertIn("obra.construtora", report.missing)
        self.assertIn("obra.nome", report.missing)

    def test_pending_always_contains_unimplemented_fields(self) -> None:
        result = map_extraction_to_partial_context(build_extraction_result(CARIMBO_TEXT))
        report = assess_extraction_coverage(result)

        self.assertIn("obra.tipo_edificacao", report.pending)
        self.assertIn("gerador.qtd", report.pending)

    def test_evidence_matches_filled_fields(self) -> None:
        result = map_extraction_to_partial_context(build_extraction_result(CARIMBO_TEXT))
        report = assess_extraction_coverage(result)

        for field_path in report.filled:
            self.assertIn(field_path, report.evidence)

    def test_nao_inclusos_always_filled(self) -> None:
        raw_text = "Texto sem sistemas especializados."
        result = map_extraction_to_partial_context(build_extraction_result(raw_text))
        report = assess_extraction_coverage(result)

        for field in ("nao_inclusos.cftv", "nao_inclusos.alarme_incendio", "nao_inclusos.automacao"):
            self.assertIn(field, report.filled)


if __name__ == "__main__":
    unittest.main()
