from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.services.context_builder import (
    build_memorial_eletrico_v1_context,
    build_memorial_gas_natural_v1_context,
    build_memorial_telecom_v1_context,
    merge_context,
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


if __name__ == "__main__":
    unittest.main()
