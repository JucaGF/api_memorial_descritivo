from __future__ import annotations

import unittest

from app.services.extraction_mapper import (
    ExtractionReport,
    FieldExtraction,
    MappingResult,
    assess_extraction_coverage,
    assess_gas_natural_extraction_coverage,
    assess_telecom_extraction_coverage,
    map_extraction_to_partial_context,
    map_extraction_to_partial_gas_natural_context,
    map_extraction_to_partial_glp_v2_context,
    map_extraction_to_partial_telecom_context,
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

REAL_TELECOM_CARIMBO_TEXT = """
DESCRIÇÃO DA MODIFICAÇÃO
QUADRO DE CONTROLE DE PROJETO
DATA
VERSÃO
engpred@gmail.com
(83)3566-0770 (83)98755-0770
ENG. EVANDRO CESAR
CREA - 16.03.55.76.10
LOCAL:
Escala:
CONSTRUTOR:
EDIFÍCIO:
PROJETO:
Desenho :
PROJETO Nº:
INDICADAS
DATA:
Projeto
Proprietário
Construtor
É EXPRESSAMENTE PROIBIDO A REPRODUÇÃO TOTAL OU PARCIAL DESTE PROJETO
MAKAI
MGA CONSTRUÇÕES E INCORPORAÇÕES LTDA
AVENIDA MAX ZAGEL, S/N, LOTE 05-A QUADRA12, CABEDELO- PB
PROJETO DE INSTALAÇÕES DE TELECOMUNICAÇÃO
23/2024
SUBSOLO
TÉRREO
PAV. 01
PAV. 02
PAV. 03
PAV. 04
PAV. 05
PAV. 06
PAV. 07
PAV. 08
COBERTA
APTO 001
APTO 101
APTO 102
APTO 103
APTO 104
APTO 201
APTO 202
APTO 203
APTO 204
APTO 301
APTO 302
APTO 303
APTO 304
APTO 401
APTO 402
APTO 403
APTO 404
APTO 501
APTO 502
APTO 503
APTO 504
APTO 601
APTO 602
APTO 603
APTO 604
APTO 701
APTO 702
APTO 703
APTO 704
APTO 801
GOURMET SOL
GOURMET MAR
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


class TelecomExtractionMapperTests(unittest.TestCase):
    def test_maps_only_telecom_relevant_obra_fields(self) -> None:
        result = map_extraction_to_partial_telecom_context(build_extraction_result(CARIMBO_TEXT))

        self.assertEqual(result.context["obra"]["construtora"], "MGA CONSTRUÇÕES E INCORPORAÇÕES LTDA")
        self.assertEqual(result.context["obra"]["nome"], "MAKAI")
        self.assertIn("CABEDELO", result.context["obra"]["localizacao"])
        self.assertNotIn("energia", result.context)
        self.assertNotIn("nao_inclusos", result.context)

    def test_telecom_coverage_marks_base_fields_and_pending_fields(self) -> None:
        result = map_extraction_to_partial_telecom_context(build_extraction_result(CARIMBO_TEXT))
        report = assess_telecom_extraction_coverage(result)

        self.assertIn("obra.construtora", report.filled)
        self.assertIn("obra.tipo_edificacao", report.pending)
        self.assertIn("obra.qtd_restaurantes", report.pending)

    def test_telecom_mapper_handles_real_carimbo_and_counts(self) -> None:
        result = map_extraction_to_partial_telecom_context(
            build_extraction_result(REAL_TELECOM_CARIMBO_TEXT)
        )
        context = result.context["obra"]

        self.assertEqual(context["construtora"], "MGA CONSTRUÇÕES E INCORPORAÇÕES LTDA")
        self.assertEqual(context["nome"], "MAKAI")
        self.assertIn("MAX ZAGEL", context["localizacao"])
        self.assertEqual(context["numero_cadastro"], "23/2024")
        self.assertEqual(context["tipo_edificacao"], "Residencial Multifamiliar")
        self.assertEqual(context["qtd_apartamentos"], 30)
        self.assertEqual(context["qtd_lojas"], 0)
        self.assertEqual(context["qtd_restaurantes"], 0)
        self.assertIn("pavimentos", context["tipologia"].lower())


class GasNaturalExtractionMapperTests(unittest.TestCase):
    def test_maps_only_gas_natural_relevant_first_pass_fields(self) -> None:
        result = map_extraction_to_partial_gas_natural_context(build_extraction_result(CARIMBO_TEXT))

        self.assertEqual(result.context["obra"]["construtora"], "MGA CONSTRUÇÕES E INCORPORAÇÕES LTDA")
        self.assertEqual(result.context["obra"]["nome"], "MAKAI")
        self.assertIn("CABEDELO", result.context["obra"]["localizacao"])
        self.assertEqual(result.context["obra"]["numero_cadastro"], "23/2024")
        self.assertNotIn("energia", result.context)
        self.assertNotIn("crm", result.context)
        self.assertNotIn("dimensionamento", result.context)

    def test_gas_natural_coverage_marks_base_fields_and_pending_fields(self) -> None:
        result = map_extraction_to_partial_gas_natural_context(build_extraction_result(CARIMBO_TEXT))
        report = assess_gas_natural_extraction_coverage(result)

        self.assertIn("obra.construtora", report.filled)
        self.assertIn("crm.pavimento", report.pending)
        self.assertIn("valvula.esfera_diametro", report.pending)

    def test_gas_natural_mapper_handles_real_carimbo_fields(self) -> None:
        result = map_extraction_to_partial_gas_natural_context(
            build_extraction_result(REAL_TELECOM_CARIMBO_TEXT)
        )
        context = result.context["obra"]

        self.assertEqual(context["construtora"], "MGA CONSTRUÇÕES E INCORPORAÇÕES LTDA")
        self.assertEqual(context["nome"], "MAKAI")
        self.assertIn("MAX ZAGEL", context["localizacao"])
        self.assertEqual(context["numero_cadastro"], "23/2024")
        self.assertEqual(context["qtd_apartamentos"], 30)

    def test_gas_natural_mapper_derives_typology_from_sheet_filenames(self) -> None:
        extraction_result = ProjectExtractionResult(
            raw_text="PROJETO DE INSTALAÇÕES DE GÁS NATURAL",
            source_files=[
                ExtractedSourceFile(
                    original_filename="01_mga_mondo_g_s_01_subsolo_ao_3_pav_18_07_2023.pdf",
                    stored_filename="01_mga_mondo_g_s_01_subsolo_ao_3_pav_18_07_2023.pdf",
                    extension=".pdf",
                    saved_path="/tmp/01_mga_mondo_g_s_01_subsolo_ao_3_pav_18_07_2023.pdf",
                    extracted_text="",
                ),
                ExtractedSourceFile(
                    original_filename="02_mga_mondo_g_s_02_4_e_5_pav_18_07_2023.pdf",
                    stored_filename="02_mga_mondo_g_s_02_4_e_5_pav_18_07_2023.pdf",
                    extension=".pdf",
                    saved_path="/tmp/02_mga_mondo_g_s_02_4_e_5_pav_18_07_2023.pdf",
                    extracted_text="",
                ),
                ExtractedSourceFile(
                    original_filename="03_mga_mondo_g_s_03_6_pav_e_cobertura_18_07_2023.pdf",
                    stored_filename="03_mga_mondo_g_s_03_6_pav_e_cobertura_18_07_2023.pdf",
                    extension=".pdf",
                    saved_path="/tmp/03_mga_mondo_g_s_03_6_pav_e_cobertura_18_07_2023.pdf",
                    extracted_text="",
                ),
            ],
            signals={"total_files": 3},
        )

        result = map_extraction_to_partial_gas_natural_context(extraction_result)

        self.assertEqual(
            result.context["obra"]["tipologia"],
            "Subsolo, 6 pavimentos, cobertura",
        )
        self.assertEqual(
            result.evidence["obra.tipologia"].rule,
            "gas_natural_sheet_filename_typology_inference",
        )

    def test_gas_natural_mapper_extracts_common_schema_fields_from_project_text(self) -> None:
        raw_text = """
        PROJETO DE INSTALAÇÕES DE GÁS NATURAL
        APTO 101 APTO 102 APTO 201 APTO 202
        CRM localizado no térreo.
        Ramal interno primário em aço carbono DN 32 mm no térreo pelo teto.
        Válvula de esfera 32 mm.
        FOGÃO: 4
        CHURRASQUEIRA: 1
        ( 1 PAVIMENTO = 5 PONTOS )
        """
        extraction_result = ProjectExtractionResult(
            raw_text=raw_text,
            source_files=[
                ExtractedSourceFile(
                    original_filename="04_mga_mondo_gas_04_corte_esquematico.pdf",
                    stored_filename="04_mga_mondo_gas_04_corte_esquematico.pdf",
                    extension=".pdf",
                    saved_path="/tmp/04_mga_mondo_gas_04_corte_esquematico.pdf",
                    extracted_text=raw_text,
                )
            ],
            signals={"total_files": 4},
        )

        result = map_extraction_to_partial_gas_natural_context(extraction_result)
        context = result.context

        self.assertEqual(context["obra"]["tipo_edificacao"], "Residencial Multifamiliar")
        self.assertEqual(context["obra"]["qtd_lojas"], 0)
        self.assertEqual(context["obra"]["qtd_restaurantes"], 0)
        self.assertEqual(context["crm"]["pavimento"], "térreo")
        self.assertEqual(context["dimensionamento"]["qtd_fogao"], 4)
        self.assertEqual(context["dimensionamento"]["qtd_aquecedor"], 0)
        self.assertEqual(context["dimensionamento"]["qtd_churrasqueira"], 1)
        self.assertEqual(context["soma"]["qtd_pontos_de_utilizacao"], 5)
        self.assertEqual(context["ramal"]["primario_diametro"], "32 mm")
        self.assertEqual(context["ramal"]["primario_material"], "aço carbono")
        self.assertEqual(context["ramal"]["primario_pavimento"], "térreo")
        self.assertEqual(context["valvula"]["esfera_diametro"], "32 mm")
        self.assertEqual(context["numero"]["prancha"], "04/04")
        self.assertEqual(context["teto_ou_piso"], "teto")


class TemGeradorHeuristicTests(unittest.TestCase):
    def test_gen_legend_without_q_board_is_not_a_generator(self) -> None:
        from app.services.extraction_mapper import _extract_tem_gerador

        text = "Legenda: simbolo de gerador segundo ABNT NBR 5410"
        ext = _extract_tem_gerador(text)
        self.assertIsNotNone(ext)
        self.assertIs(ext.value, False)

    def test_q_ger_panel_snippet_implies_generator(self) -> None:
        from app.services.extraction_mapper import _extract_tem_gerador

        text = "Painel Q-GER-01 alimenta cargas essenciais no diagrama."
        ext = _extract_tem_gerador(text)
        self.assertIsNotNone(ext)
        self.assertIs(ext.value, True)

    def test_q_board_without_atendimento_keywords_yields_null_tipo(self) -> None:
        from app.services.extraction_mapper import _extract_gerador_tipo_atendimento

        text = "Q-GER-01 sem listagem de unidades habitacionais"
        self.assertIsNone(_extract_gerador_tipo_atendimento(text))


class GlpV2MapperTests(unittest.TestCase):
    def test_map_does_not_accept_apartment_number_as_fogao_quantity(self) -> None:
        raw = """
        APTO 801
        FOGÕES
        Ramal secundário 16mm.
        """
        result = map_extraction_to_partial_glp_v2_context(build_extraction_result(raw))

        self.assertNotIn("qtd_fogao", result.context.get("dimensionamento", {}))
        self.assertNotIn("dimensionamento.qtd_fogao", result.evidence)

    def test_unique_apartment_ids_are_low_confidence_visual_labels(self) -> None:
        raw = """
        APTO 101 APTO 102 APTO 201 APTO 202
        APTO 301 APTO 302 APTO 401 APTO 402
        """
        result = map_extraction_to_partial_glp_v2_context(build_extraction_result(raw))

        self.assertEqual(result.context["obra"]["qtd_apartamentos"], 8)
        self.assertEqual(result.evidence["obra.qtd_apartamentos"].rule, "unique_apartment_ids")
        self.assertEqual(result.evidence["obra.qtd_apartamentos"].confidence, "low")

    def test_map_does_not_read_decimal_heights_as_point_quantities(self) -> None:
        raw = """
        Vista frontal ponto gás p/ fogão 0.60 Fogão 0.60 Fogão.
        Ramal secundário 16mm.
        0,30 Churrasqueira 7.000 Kcal/h.
        """
        result = map_extraction_to_partial_glp_v2_context(build_extraction_result(raw))
        dimensionamento = result.context.get("dimensionamento", {})

        self.assertNotIn("qtd_fogao", dimensionamento)
        self.assertNotIn("qtd_churrasqueira", dimensionamento)

    def test_map_fills_main_diameter_near_ramal_keyword(self) -> None:
        raw = """
        Ramal primário em aço carbono com tubo 1 1/4" até o abrigo GLP.
        """
        result = map_extraction_to_partial_glp_v2_context(build_extraction_result(raw))
        diam = result.context.get("diametros", {}).get("tubulacao_principal")
        self.assertIsInstance(diam, dict)
        self.assertEqual(diam["unidade"], "in")

    def test_critical_conflict_when_fogao_equals_apartments_regex(self) -> None:
        raw = """
        Empreendimento com 29 apartamentos.
        Foram previstos 29 fogões.
        """
        result = map_extraction_to_partial_glp_v2_context(build_extraction_result(raw))
        conflicts = result.context.get("_glp_v2_critical_conflicts", [])
        self.assertTrue(any(c.get("tipo") == "glp_v2_fogao_apartamentos_colision" for c in conflicts))


    def test_map_prefers_main_pipe_diameter_over_secondary_branch(self) -> None:
        raw = """
        Ramal Secundário 16mm em multicamadas para pontos internos.
        Ramal primário em aço carbono SCH 40 com tubo 1 1/4" até o abrigo GLP.
        """
        result = map_extraction_to_partial_glp_v2_context(build_extraction_result(raw))
        diam = result.context.get("diametros", {}).get("tubulacao_principal")

        self.assertEqual(diam["valor_formatado"], '1 1/4"')


if __name__ == "__main__":
    unittest.main()
