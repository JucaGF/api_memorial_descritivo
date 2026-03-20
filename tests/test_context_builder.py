from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.services.context_builder import build_memorial_eletrico_v1_context


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


if __name__ == "__main__":
    unittest.main()
