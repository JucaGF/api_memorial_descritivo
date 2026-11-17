from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.services.context_builder import (
    build_memorial_eletrico_canteiro_v1_context,
    build_memorial_eletrico_v1_context,
)
from app.services.memorial_renderer import (
    ELETRICO_CANTEIRO_V1_TEMPLATE_PATH,
    MemorialRenderError,
    assert_no_internal_markers_left,
    assert_no_jinja_left,
    has_docx_render_dependencies,
    inspect_docx_text,
    render_memorial_eletrico_canteiro_v1,
    render_memorial_eletrico_v1,
    render_memorial_gas_natural_v1,
    render_memorial_glp_v2,
    render_memorial_telecom_v1,
)
from app.services.memorial_validator import (
    validate_memorial_eletrico_canteiro_v1_context,
    validate_memorial_eletrico_v1_context,
    validate_memorial_gas_natural_v1_context,
    validate_memorial_glp_v2_context,
    validate_memorial_telecom_v1_context,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "eletrico_sem_subestacao.json"
TELECOM_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "telecom_base.json"
GAS_NATURAL_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "gas_natural_base.json"
CANTEIRO_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "eletrico_canteiro_bothanic_expected.json"


def load_fixture() -> dict:
    with FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_telecom_fixture() -> dict:
    with TELECOM_FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_gas_natural_fixture() -> dict:
    with GAS_NATURAL_FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_valid_context() -> dict:
    context = build_memorial_eletrico_v1_context(load_fixture())
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


def build_eletrico_context_without_generator() -> dict:
    context = load_fixture()
    context["gerador"] = {
        "tem_gerador": False,
        "qtd": 0,
        "potencia_kva": 0,
        "tipo_atendimento": "condominio",
        "circuitos_atendidos": None,
    }
    built = build_memorial_eletrico_v1_context(context)
    validate_memorial_eletrico_v1_context(built)
    return built


def build_valid_telecom_context() -> dict:
    context = load_telecom_fixture()
    validate_memorial_telecom_v1_context(context)
    return context


def build_valid_gas_natural_context() -> dict:
    context = load_gas_natural_fixture()
    validate_memorial_gas_natural_v1_context(context)
    return context


def build_valid_glp_v2_context() -> dict:
    context = {
        "documento": {"data_atual": "13/05/2026"},
        "obra": {
            "numero_cadastro": "12345/2026",
            "construtora": "MGA CONSTRUCOES",
            "nome": "MAKAI",
            "localizacao": "Rua Exemplo, 100",
            "tipo_edificacao": "Residencial multifamiliar",
            "tipologia": "Subsolo, terreo, pavimentos tipo e cobertura",
            "qtd_apartamentos": {
                "valor": 29,
                "confianca": "high",
                "fonte_evidencia": [
                    {
                        "texto": "29 apartamentos",
                        "regra": "fixture_glp_v2_renderer",
                        "confianca": "high",
                    }
                ],
            },
            "qtd_lojas": 0,
            "qtd_restaurantes": 0,
        },
        "tanques": {
            "quantidade": 1,
            "tipo": "P-190",
            "capacidade_kg": 190,
            "qtd_abrigos": 1,
            "qtd_recipientes": 2,
            "fonte_evidencia": [
                {
                    "texto": "Abrigo de gas P-190",
                    "regra": "fixture_glp_v2_renderer",
                    "confianca": "high",
                }
            ],
            "conflitos": [],
        },
        "abastecimento": {"pavimento": "terreo"},
        "dimensionamento": {
            "qtd_fogao": 35,
            "qtd_aquecedor": 0,
            "qtd_churrasqueira": 35,
            "qtd_outros": 0,
        },
        "pontos_utilizacao": {
            "fogao": 35,
            "churrasqueira": 35,
            "aquecedor": 0,
            "outros": 0,
            "total_extraido": 70,
            "total_calculado": 70,
            "fontes_evidencia": [
                {
                    "texto": "35 fogoes e 35 churrasqueiras",
                    "regra": "fixture_glp_v2_renderer",
                    "confianca": "high",
                }
            ],
            "conflitos": [],
        },
        "diametros": {
            "tubulacao_principal": {
                "valor": 1.25,
                "unidade": "in",
                "valor_formatado": '1 1/4"',
                "valor_original": '1 1/4"',
            },
            "valvula_esfera": {
                "valor": 1.25,
                "unidade": "in",
                "valor_formatado": '1 1/4"',
                "valor_original": '1 1/4"',
                "inferido": True,
            },
        },
        "ramal": {
            "primario_material": "aco carbono SCH 40",
            "primario_pavimento": "terreo",
        },
        "numero": {"prancha": "01/04"},
        "teto_ou_piso": "piso",
        "context_version": "glp_v2",
        "template_version": "glp_v2",
    }
    validate_memorial_glp_v2_context(context)
    return context


def load_canteiro_fixture() -> dict:
    with CANTEIRO_FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_valid_canteiro_context(payload: dict | None = None) -> dict:
    context = build_memorial_eletrico_canteiro_v1_context(
        payload if payload is not None else load_canteiro_fixture()
    )
    validate_memorial_eletrico_canteiro_v1_context(context)
    return context


def render_canteiro_text(context: dict, filename: str) -> str:
    output_path = ROOT / "tests" / "output" / filename
    render_memorial_eletrico_canteiro_v1(context, output_path)
    return inspect_docx_text(output_path)


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
        self.assertIn("GRUPO GERADOR", text)

    @unittest.skipUnless(
        has_docx_render_dependencies(),
        "python-docx e docxtpl nao estao instalados no ambiente",
    )
    def test_render_memorial_eletrico_v1_omits_generator_section_when_absent(self) -> None:
        tmp_dir = ROOT / "tests" / "output"
        output_path = tmp_dir / "renderer_test_output_eletrico_sem_gerador.docx"

        render_memorial_eletrico_v1(build_eletrico_context_without_generator(), output_path)

        text = inspect_docx_text(output_path)
        self.assertNotIn("GRUPO GERADOR", text)
        self.assertNotIn("grupo geradores a diesel", text)

    def test_eletrico_context_keeps_mt_tension_empty_when_missing(self) -> None:
        context = build_memorial_eletrico_v1_context({"energia": {"tem_subestacao": False}})

        self.assertEqual(context["mt"], {})

    @unittest.skipUnless(
        has_docx_render_dependencies(),
        "python-docx e docxtpl nao estao instalados no ambiente",
    )
    def test_render_memorial_eletrico_v1_leaves_mt_section_blank_when_missing(self) -> None:
        tmp_dir = ROOT / "tests" / "output"
        output_path = tmp_dir / "renderer_test_output_eletrico_mt_blank.docx"
        context = build_valid_context()
        context["mt"] = {}

        render_memorial_eletrico_v1(context, output_path)

        text = inspect_docx_text(output_path)
        self.assertIn("circuito de  kV", text)
        self.assertNotIn("13.8", text)
        self.assertNotIn("13,8", text)
        self.assertNotIn("circuito de 13.8 kV", text)
        self.assertNotIn("circuito de 13,8 kV", text)

    @unittest.skipUnless(
        has_docx_render_dependencies(),
        "python-docx e docxtpl nao estao instalados no ambiente",
    )
    def test_render_memorial_telecom_v1_generates_docx_without_template_tokens(self) -> None:
        tmp_dir = ROOT / "tests" / "output"
        output_path = tmp_dir / "renderer_test_output_telecom.docx"

        render_memorial_telecom_v1(build_valid_telecom_context(), output_path)

        self.assertTrue(output_path.exists())
        text = inspect_docx_text(output_path)
        self.assertNotIn("{{", text)
        self.assertNotIn("{%", text)

    @unittest.skipUnless(
        has_docx_render_dependencies(),
        "python-docx e docxtpl nao estao instalados no ambiente",
    )
    def test_render_memorial_gas_natural_v1_generates_docx_without_template_tokens(self) -> None:
        tmp_dir = ROOT / "tests" / "output"
        output_path = tmp_dir / "renderer_test_output_gas_natural.docx"

        render_memorial_gas_natural_v1(build_valid_gas_natural_context(), output_path)

        self.assertTrue(output_path.exists())
        text = inspect_docx_text(output_path)
        self.assertNotIn("{{", text)
        self.assertNotIn("{%", text)

    @unittest.skipUnless(
        has_docx_render_dependencies(),
        "python-docx e docxtpl nao estao instalados no ambiente",
    )
    def test_render_memorial_gas_natural_v1_renders_valvula_esfera_diametro(self) -> None:
        tmp_dir = ROOT / "tests" / "output"
        output_path = tmp_dir / "renderer_test_output_gas_natural_valvula.docx"

        render_memorial_gas_natural_v1(build_valid_gas_natural_context(), output_path)

        text = inspect_docx_text(output_path)
        self.assertIn("32 mm", text)

    @unittest.skipUnless(
        has_docx_render_dependencies(),
        "python-docx e docxtpl nao estao instalados no ambiente",
    )
    def test_render_memorial_glp_v2_preserves_inch_diameters_and_schema_fields(self) -> None:
        tmp_dir = ROOT / "tests" / "output"
        output_path = tmp_dir / "renderer_test_output_glp_v2.docx"

        render_memorial_glp_v2(build_valid_glp_v2_context(), output_path)

        self.assertTrue(output_path.exists())
        text = inspect_docx_text(output_path)
        self.assertNotIn("{{", text)
        self.assertNotIn("{%", text)
        self.assertNotIn("1.25mm", text)
        self.assertNotIn('1 1/4"mm', text)
        self.assertIn("MEMORIAL DESCRITIVO", text)
        self.assertIn("INSTALAÇÕES PREDIAIS DE GLP", text)
        self.assertIn('terá diâmetro de 1 1/4"', text)
        self.assertIn('válvula de esfera de 1 1/4"', text)
        self.assertIn("Fogão 04 bocas: 7.000 Kcal/h (35 unidades)", text)
        self.assertIn("Churrasqueira 04 bocas: 7.000 Kcal/h (35", text)
        self.assertIn("Totalizando 70 pontos de utilização", text)

    def test_glp_v2_template_uses_schema_v2_placeholders_not_legacy_v1_paths(self) -> None:
        from docx import Document

        template_text = "\n".join(
            paragraph.text for paragraph in Document(ROOT / "templates" / "glp" / "v2" / "template.docx").paragraphs
        )

        self.assertIn("{{ obra.qtd_apartamentos.valor }}", template_text)
        self.assertIn("{{ tanques.qtd_abrigos }}", template_text)
        self.assertNotIn("{{ tanques.quantidade }}", template_text)
        self.assertIn("{{ pontos_utilizacao.fogao }}", template_text)
        self.assertIn("{{ pontos_utilizacao.total_calculado }}", template_text)
        self.assertIn("{{ diametros.tubulacao_principal.valor_formatado }}", template_text)
        self.assertIn("{{ diametros.valvula_esfera.valor_formatado }}", template_text)
        self.assertNotIn("{{ obra.qtd_apartamentos }}", template_text)
        self.assertNotIn("{{ abastecimento.qtd_tanques }}", template_text)
        self.assertNotIn("{{ soma.qtd_pontos_de_utilizacao }}", template_text)
        self.assertNotIn("{{ ramal.primario_diametro }}", template_text)
        self.assertNotIn("xxxx", template_text)

    def test_assert_no_jinja_left_raises_structured_error(self) -> None:
        with self.assertRaises(MemorialRenderError) as error_info:
            assert_no_jinja_left("trecho com {{ placeholder }}")

        self.assertIn("Jinja", str(error_info.exception))

    def test_assert_no_internal_markers_left_raises_structured_error(self) -> None:
        with self.assertRaises(MemorialRenderError) as error_info:
            assert_no_internal_markers_left("Texto Fixo do template")

        self.assertIn("template", str(error_info.exception))


@unittest.skipUnless(
    has_docx_render_dependencies(),
    "python-docx e docxtpl nao estao instalados no ambiente",
)
class EletricoCanteiroRendererTests(unittest.TestCase):
    def test_render_canteiro_bothanic_has_no_template_tokens(self) -> None:
        output_path = ROOT / "tests" / "output" / "renderer_test_output_canteiro.docx"

        render_memorial_eletrico_canteiro_v1(build_valid_canteiro_context(), output_path)

        self.assertTrue(output_path.exists())
        text = inspect_docx_text(output_path)
        self.assertNotIn("{{", text)
        self.assertNotIn("{%", text)
        self.assertIn(
            "MEMORIAL DESCRITIVO E ESPECIFICAÇÕES TÉCNICAS DAS INSTALAÇÕES "
            "ELÉTRICAS-BT DO CANTEIRO DE OBRAS DO BOTHANIC",
            text,
        )
        self.assertIn("SUBESTAÇÃO AÉREA", text)
        self.assertIn("75 kVA", text)
        # Mesmo formato do template eletrico: "MT-{{ mt.tensao_kv }}kV".
        self.assertIn("MT-13.8kV", text)
        self.assertIn(
            "completa execução das instalações elétricas do canteiro de obras "
            "do empreendimento, conforme abaixo descrito.",
            text,
        )
        self.assertIn("NORMAS CONSIDERADAS NO PROJETO", text)
        self.assertIn("EQUIPAMENTOS DO CANTEIRO DE OBRAS", text)
        self.assertIn("QUADROS DE DISTRIBUIÇÃO NO CANTEIRO DE OBRAS", text)
        self.assertIn("6. NORMAS CONSIDERADAS NO PROJETO", text)
        self.assertIn("7. EQUIPAMENTOS DO CANTEIRO DE OBRAS", text)
        self.assertIn("8. QUADROS DE DISTRIBUIÇÃO NO CANTEIRO DE OBRAS", text)
        self.assertIn("4.10. MONTAGEM DOS APARELHOS", text)
        self.assertIn(
            "conectados à malha de aterramento do canteiro, composta de 3 hastes",
            text,
        )
        self.assertIn("cabo de cobre nu de 50 mm²", text)
        self.assertNotIn("Centro de Convenções", text)
        self.assertNotIn("None", text)

    def test_render_canteiro_lists_real_quadros_with_loads(self) -> None:
        text = render_canteiro_text(
            build_valid_canteiro_context(), "renderer_test_output_canteiro_quadros.docx"
        )
        lines = text.splitlines()

        self.assertIn("Q.G.B.T. – 89.088 W", text)
        self.assertIn("Q.D.MÓVEL – 3.851 W", text)
        self.assertIn(
            "Q.D.L/T TORRE – 12.714 W: Circuitos de iluminação e tomadas para uso "
            "durante a execução da obra.",
            lines,
        )
        self.assertIn("Q.D.ELEV. CREMALHEIRA – 13.800 W", lines)

    def test_render_canteiro_omits_building_and_bep_and_gerador_text(self) -> None:
        text = render_canteiro_text(
            build_valid_canteiro_context(), "renderer_test_output_canteiro_omissoes.docx"
        )
        lines = [line.strip() for line in text.splitlines()]

        for absent in (
            "Quantidade de apartamentos",
            "Tipo de Edificação",
            "Tipologia",
            "BEP",
            "GRUPO GERADOR",
            "ITENS NÃO INCLUSOS",
            "DADOS CONSTRUTIVOS DA SUBESTAÇÃO",
            "SPDA",
            "Ligações Equipotenciais",
            "conforme construído",
            "firma instaladora",
            "INSS",
            "projeto luminotécnico das áreas comuns",
            "geradores a diesel",
        ):
            self.assertNotIn(absent, text)
        # O exemplo mantém "ACESSÓRIOS DE FIXAÇÃO DE PERFILADOS E ELETROCALHA";
        # o que sai são os blocos com estes títulos.
        for absent_heading in (
            "PERFILADO",
            "SUPORTES PARA PERFILADOS",
            "ELETROCALHAS",
            "CONDULETES",
            "TOMADAS DE FORÇA – ÁREA EXTERNA",
        ):
            self.assertNotIn(absent_heading, lines)

    def test_render_canteiro_keeps_material_spec_blocks_from_example(self) -> None:
        text = render_canteiro_text(
            build_valid_canteiro_context(), "renderer_test_output_canteiro_materiais.docx"
        )
        lines = [line.strip() for line in text.splitlines()]

        for heading in (
            "ELETRODUTOS DE AÇO GALVANIZADO, CURVAS E LUVAS",
            "ELETRODUTOS DE PVC, CURVAS E LUVAS",
            "CAIXAS ESTAMPADAS",
            "VERGALHÃO COM ROSCA TOTAL",
            "ACESSÓRIOS DE FIXAÇÃO DE PERFILADOS E ELETROCALHA",
            "ELETRODUTO FLEXÍVEL PARA LIGAÇÃO DE MOTORES",
            "BUCHAS E ARRUELAS",
            "INTERRUPTORES",
            "TOMADAS DE USO GERAL",
            "ELETRODUTO CORRUGADO TIPO PEAD",
        ):
            self.assertIn(heading, lines)

    def test_render_canteiro_escapes_special_characters_in_values(self) -> None:
        context = build_valid_canteiro_context()
        self.assertEqual(context["obra"]["construtora"], "MOREIRA & RUFFO'S LTDA")

        text = render_canteiro_text(context, "renderer_test_output_canteiro_escape.docx")

        self.assertIn("Construtora: MOREIRA & RUFFO'S LTDA;", text.splitlines())

    def test_render_canteiro_equipment_without_potencia_has_no_placeholder_text(self) -> None:
        payload = load_canteiro_fixture()
        payload["equipamentos"][0]["qtd"] = 2
        text = render_canteiro_text(
            build_valid_canteiro_context(payload),
            "renderer_test_output_canteiro_equipamentos.docx",
        )
        lines = text.splitlines()

        self.assertIn("Mini guincho: 01 unidade", lines)
        self.assertIn("Elevador cremalheira: 01 unidade", lines)
        self.assertIn("Esmeril 1/4 CV: 01 unidade", lines)
        self.assertIn("Betoneira 7,5 CV: 02 unidades", lines)
        self.assertNotIn("None", text)
        self.assertNotIn("()", text)

    def test_render_canteiro_without_subestacao_omits_section_and_renumbers(self) -> None:
        payload = load_canteiro_fixture()
        payload["energia"] = {"tem_subestacao": False}
        text = render_canteiro_text(
            build_valid_canteiro_context(payload),
            "renderer_test_output_canteiro_sem_subestacao.docx",
        )

        self.assertNotIn("SUBESTAÇÃO AÉREA", text)
        self.assertNotIn("kVA", text)
        self.assertIn("4.2. ATERRAMENTO", text)
        self.assertIn("4.9. MONTAGEM DOS APARELHOS", text)
        self.assertNotIn("4.10.", text)
        self.assertIn("não sendo prevista subestação", text)
        self.assertNotIn("Barramento de MT", text)
        self.assertNotIn("None", text)

    def test_render_canteiro_without_mt_cabo_omits_mt_paragraphs(self) -> None:
        context = build_valid_canteiro_context()
        self.assertIsNone(context["mt"]["secao_cabo_mm2"])
        self.assertIsNone(context["mt"]["diametro_eletroduto_pol"])

        text = render_canteiro_text(context, "renderer_test_output_canteiro_sem_mt.docx")

        for absent in (
            "8,7/15",
            "35mm²",
            "35 mm²",
            "Ramal de MT",
            "Ramal subterrâneo de MT",
            "condutores do circuito de",
            "envelopados em concreto",
            "None",
        ):
            self.assertNotIn(absent, text)
        self.assertIn("Alimentações em BT:", text)

    def test_render_canteiro_with_mt_cabo_renders_values(self) -> None:
        payload = load_canteiro_fixture()
        payload["mt"].update(
            {
                "secao_cabo_mm2": 35,
                "diametro_eletroduto_pol": 4,
                "tipo_cabo": "EPR/XLPE",
                "temperatura_cabo": 90,
                "classe_isolacao": "8,7/15",
            }
        )
        text = render_canteiro_text(
            build_valid_canteiro_context(payload),
            "renderer_test_output_canteiro_com_mt.docx",
        )

        self.assertIn("Ramal de MT – 13.8 kV:", text)
        self.assertIn(
            "será executado por cabos EPR/XLPE a 90° com isolação para 8,7/15 kV, "
            "secção 35 mm².",
            text,
        )
        self.assertIn("circuito de 13.8 kV", text)
        self.assertIn("na bitola de 4”", text)
        self.assertNotIn("None", text)

    def test_render_canteiro_mt_cabo_prints_only_filled_cable_attributes(self) -> None:
        payload = load_canteiro_fixture()
        payload["mt"]["secao_cabo_mm2"] = 35
        text = render_canteiro_text(
            build_valid_canteiro_context(payload),
            "renderer_test_output_canteiro_mt_parcial.docx",
        )

        self.assertIn("será executado por cabos, secção 35 mm².", text)
        self.assertNotIn("isolação para", text)
        self.assertNotIn("°, ", text)
        self.assertNotIn("None", text)
        self.assertNotIn("condutores do circuito de", text)

    def test_canteiro_template_keeps_each_jinja_tag_in_a_single_run(self) -> None:
        from docx import Document

        document = Document(str(ELETRICO_CANTEIRO_V1_TEMPLATE_PATH))
        for paragraph in document.paragraphs:
            for run in paragraph.runs:
                run_text = run.text
                self.assertEqual(
                    run_text.count("{{"), run_text.count("}}"), f"run partido: {run_text!r}"
                )
                self.assertEqual(
                    run_text.count("{%"), run_text.count("%}"), f"run partido: {run_text!r}"
                )
            if "{%p" in paragraph.text:
                self.assertTrue(
                    paragraph.text.strip().startswith("{%p")
                    and paragraph.text.strip().endswith("%}")
                    and paragraph.text.count("{%") == 1,
                    f"tag de paragrafo fora de paragrafo proprio: {paragraph.text!r}",
                )


if __name__ == "__main__":
    unittest.main()
