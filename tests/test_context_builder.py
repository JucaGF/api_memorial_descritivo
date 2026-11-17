from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.services.context_builder import (
    CANTEIRO_DEFAULTS,
    QUADRO_DESCRICOES_CONHECIDAS,
    build_memorial_eletrico_canteiro_v1_context,
    build_memorial_eletrico_v1_context,
    build_memorial_gas_natural_v1_context,
    build_memorial_telecom_v1_context,
    merge_context,
    normalize_quadro_key,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures"


def load_fixture(filename: str) -> dict:
    with (FIXTURES_DIR / filename).open("r", encoding="utf-8") as file:
        return json.load(file)


class ContextBuilderTests(unittest.TestCase):
    def test_recomputes_nao_inclusos_tem_itens_ignoring_input_value(self) -> None:
        payload = load_fixture("eletrico_com_subestacao.json")
        payload["nao_inclusos"]["tem_itens"] = False

        context = build_memorial_eletrico_v1_context(payload)

        self.assertTrue(context["nao_inclusos"]["tem_itens"])

    def test_preserves_circuitos_atendidos_when_tipo_atendimento_is_parcial(self) -> None:
        payload = load_fixture("eletrico_sem_subestacao.json")

        context = build_memorial_eletrico_v1_context(payload)

        self.assertEqual(
            context["gerador"]["circuitos_atendidos"],
            "bombas, elevadores e iluminação de emergência",
        )

    def test_sets_circuitos_atendidos_to_null_when_tipo_atendimento_is_not_parcial(self) -> None:
        payload = load_fixture("eletrico_com_subestacao.json")
        payload["gerador"]["circuitos_atendidos"] = "valor inconsistente"

        context = build_memorial_eletrico_v1_context(payload)

        self.assertIsNone(context["gerador"]["circuitos_atendidos"])

    def test_fills_nullable_energia_fields_with_null_when_sem_subestacao(self) -> None:
        payload = load_fixture("eletrico_sem_subestacao.json")
        del payload["energia"]["tipo_subestacao"]
        del payload["energia"]["potencia_transformador_kva"]

        context = build_memorial_eletrico_v1_context(payload)

        self.assertIsNone(context["energia"]["tipo_subestacao"])
        self.assertIsNone(context["energia"]["potencia_transformador_kva"])

    def test_does_not_mutate_original_input_payload(self) -> None:
        payload = load_fixture("eletrico_com_subestacao.json")
        payload["nao_inclusos"]["tem_itens"] = False

        context = build_memorial_eletrico_v1_context(payload)

        self.assertFalse(payload["nao_inclusos"]["tem_itens"])
        self.assertTrue(context["nao_inclusos"]["tem_itens"])

    def test_telecom_fills_documento_data_atual_when_missing(self) -> None:
        payload = load_fixture("telecom_base.json")
        del payload["documento"]["data_atual"]

        context = build_memorial_telecom_v1_context(payload)

        self.assertIn("data_atual", context["documento"])
        self.assertTrue(context["documento"]["data_atual"])

    def test_telecom_does_not_mutate_original_input_payload(self) -> None:
        payload = load_fixture("telecom_base.json")
        del payload["documento"]["data_atual"]

        context = build_memorial_telecom_v1_context(payload)

        self.assertNotIn("data_atual", payload["documento"])
        self.assertIn("data_atual", context["documento"])

    def test_gas_natural_fills_documento_data_atual_when_missing(self) -> None:
        payload = load_fixture("gas_natural_base.json")
        del payload["documento"]["data_atual"]

        context = build_memorial_gas_natural_v1_context(payload)

        self.assertIn("data_atual", context["documento"])
        self.assertTrue(context["documento"]["data_atual"])

    def test_gas_natural_does_not_mutate_original_input_payload(self) -> None:
        payload = load_fixture("gas_natural_base.json")
        del payload["documento"]["data_atual"]

        context = build_memorial_gas_natural_v1_context(payload)

        self.assertNotIn("data_atual", payload["documento"])
        self.assertIn("data_atual", context["documento"])


class MergeContextTests(unittest.TestCase):
    def test_merge_adds_new_keys_from_overrides(self) -> None:
        base = {"obra": {"nome": "Edifício A"}}
        overrides = {"obra": {"construtora": "Empresa X LTDA"}}

        result = merge_context(base, overrides)

        self.assertEqual(result["obra"]["nome"], "Edifício A")
        self.assertEqual(result["obra"]["construtora"], "Empresa X LTDA")

    def test_merge_overrides_override_base_values(self) -> None:
        base = {"obra": {"nome": "Nome Antigo"}}
        overrides = {"obra": {"nome": "Nome Correto"}}

        result = merge_context(base, overrides)

        self.assertEqual(result["obra"]["nome"], "Nome Correto")

    def test_merge_is_deep_not_shallow(self) -> None:
        base = {"obra": {"nome": "A", "localizacao": "Rua X"}, "energia": {"tem_subestacao": False}}
        overrides = {"obra": {"construtora": "Empresa Y LTDA"}}

        result = merge_context(base, overrides)

        self.assertEqual(result["obra"]["nome"], "A")
        self.assertEqual(result["obra"]["localizacao"], "Rua X")
        self.assertEqual(result["obra"]["construtora"], "Empresa Y LTDA")
        self.assertFalse(result["energia"]["tem_subestacao"])

    def test_merge_does_not_mutate_base(self) -> None:
        base = {"obra": {"nome": "Original"}}
        overrides = {"obra": {"nome": "Modificado"}}

        merge_context(base, overrides)

        self.assertEqual(base["obra"]["nome"], "Original")

    def test_merge_does_not_mutate_overrides(self) -> None:
        base = {"obra": {"nome": "A"}}
        overrides = {"obra": {"construtora": "B LTDA"}}

        merge_context(base, overrides)

        self.assertNotIn("nome", overrides["obra"])

    def test_merge_accumulates_across_multiple_patches(self) -> None:
        base = {"obra": {}}
        patch1 = {"obra": {"nome": "Makai"}}
        patch2 = {"obra": {"construtora": "MGA LTDA"}}

        after_first = merge_context(base, patch1)
        after_second = merge_context(after_first, patch2)

        self.assertEqual(after_second["obra"]["nome"], "Makai")
        self.assertEqual(after_second["obra"]["construtora"], "MGA LTDA")


class CanteiroContextBuilderTests(unittest.TestCase):
    def test_canteiro_builder_defaults_mt_tensao_to_13_8(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context({"mt": {}})
        self.assertEqual(ctx["mt"]["tensao_kv"], 13.8)

    def test_canteiro_builder_keeps_extracted_mt_tensao(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context({"mt": {"tensao_kv": 13.2}})
        self.assertEqual(ctx["mt"]["tensao_kv"], 13.2)

    def test_canteiro_builder_does_not_default_mt_eletroduto_or_cabo(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context({"mt": {}})
        for key in (
            "diametro_eletroduto_pol",
            "secao_cabo_mm2",
            "tipo_cabo",
            "temperatura_cabo",
            "classe_isolacao",
        ):
            self.assertIsNone(ctx["mt"].get(key))

    def test_canteiro_builder_applies_fixed_defaults(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context({})
        self.assertEqual(ctx["aterramento"]["tipo_sistema"], "TN-S")
        self.assertEqual(
            ctx["energia"]["tensao_secundaria"],
            "380 V entre fases e 220 V entre fases e neutro",
        )
        self.assertTrue(ctx["energia"]["tap_descricao"].startswith("Tap 1 – 13.800 V;"))
        self.assertEqual(ctx["obra"]["porcentagem_entre_trafos"], "2%")
        self.assertEqual(ctx["obra"]["porcentagem_entre_quadros"], "3%")
        self.assertTrue(ctx["documento"]["data_atual"])

    def test_canteiro_builder_extracted_values_beat_defaults(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context(
            {"aterramento": {"tipo_sistema": "TT"}, "energia": {"tensao_secundaria": "x"}}
        )
        self.assertEqual(ctx["aterramento"]["tipo_sistema"], "TT")
        self.assertEqual(ctx["energia"]["tensao_secundaria"], "x")

    def test_canteiro_builder_does_not_mutate_defaults_or_input(self) -> None:
        payload = {"mt": {}}
        build_memorial_eletrico_canteiro_v1_context(payload)
        self.assertEqual(payload, {"mt": {}})
        self.assertNotIn("diametro_eletroduto_pol", CANTEIRO_DEFAULTS["mt"])

    def test_canteiro_builder_nulls_substation_fields_without_subestacao(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context(
            {"energia": {"tem_subestacao": False}}
        )
        for key in ("tipo_subestacao", "potencia_transformador_kva", "tap_descricao", "tensao_secundaria"):
            self.assertIn(key, ctx["energia"])

    def test_canteiro_builder_uses_engineer_description_for_torre(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context(
            {"quadros": [{"nome": "Q.D.L/T TORRE", "carga_w": 12714}]}
        )
        self.assertEqual(
            ctx["quadros"][0]["descricao"],
            "Circuitos de iluminação e tomadas para uso durante a execução da obra.",
        )

    def test_canteiro_builder_formats_quadro_load_and_known_description(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context(
            {"quadros": [{"nome": "Q.G.B.T.", "carga_w": 89088}]}
        )
        self.assertEqual(ctx["quadros"][0]["carga_formatada"], "89.088 W")
        self.assertEqual(
            ctx["quadros"][0]["descricao"],
            "Concentra todos os demais quadros e equipamentos específicos de maior potência.",
        )

    def test_canteiro_builder_unknown_quadro_gets_null_description(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context(
            {"quadros": [{"nome": "Q.D.BOMBAS", "carga_w": 1000}]}
        )
        self.assertIsNone(ctx["quadros"][0]["descricao"])
        self.assertEqual(ctx["quadros"][0]["carga_formatada"], "1.000 W")

    def test_canteiro_builder_cremalheira_has_no_description(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context(
            {"quadros": [{"nome": "Q.D.ELEV. CREMALHEIRA", "carga_w": 13800}]}
        )
        self.assertIsNone(ctx["quadros"][0]["descricao"])

    def test_canteiro_known_descriptions_keys(self) -> None:
        self.assertEqual(
            set(QUADRO_DESCRICOES_CONHECIDAS),
            {"QGBT", "QDLTTORRE", "QDAPOIO", "QDSTAND", "QDMOVEL"},
        )

    def test_canteiro_builder_normalizes_name_accents_and_case(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context(
            {"quadros": [{"nome": "q.d. móvel", "carga_w": 3851}]}
        )
        self.assertEqual(
            ctx["quadros"][0]["descricao"],
            "Equipamentos móveis, como guinchos e vibradores.",
        )

    def test_canteiro_builder_keeps_explicit_description(self) -> None:
        ctx = build_memorial_eletrico_canteiro_v1_context(
            {"quadros": [{"nome": "Q.G.B.T.", "carga_w": 1, "descricao": "custom"}]}
        )
        self.assertEqual(ctx["quadros"][0]["descricao"], "custom")

    def test_normalize_quadro_key_ignores_punctuation_spaces_case_and_accents(self) -> None:
        self.assertEqual(normalize_quadro_key("Q.G.B.T."), normalize_quadro_key("q.g.b.t"))
        self.assertEqual(normalize_quadro_key("Q.D. MÓVEL"), "QDMOVEL")
        self.assertEqual(normalize_quadro_key(None), "")


if __name__ == "__main__":
    unittest.main()
