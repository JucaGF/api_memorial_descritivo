from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.services.memorial_validator import (
    MemorialValidationError,
    load_eletrico_v1_schema,
    load_gas_natural_v1_schema,
    load_glp_v1_schema,
    load_glp_v2_schema,
    load_telecom_v1_schema,
    validate_memorial_eletrico_v1_context,
    validate_memorial_gas_natural_v1_context,
    validate_memorial_glp_v1_context,
    validate_memorial_glp_v2_context,
    validate_memorial_telecom_v1_context,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "eletrico_sem_subestacao.json"
TELECOM_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "telecom_base.json"
GAS_NATURAL_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "gas_natural_base.json"
GLP_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "glp_base.json"


def load_fixture() -> dict:
    with FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_telecom_fixture() -> dict:
    with TELECOM_FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_gas_natural_fixture() -> dict:
    with GAS_NATURAL_FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_glp_fixture() -> dict:
    with GLP_FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


class MemorialValidatorTests(unittest.TestCase):
    def test_load_eletrico_v1_schema_returns_expected_contract(self) -> None:
        schema = load_eletrico_v1_schema()

        self.assertEqual(schema["title"], "MemorialEletricoContextV1")
        self.assertIn("obra", schema["required"])

    def test_validate_memorial_eletrico_v1_context_accepts_valid_fixture(self) -> None:
        context = load_fixture()
        context["nao_inclusos"]["tem_itens"] = any(context["nao_inclusos"].values())

        issues = validate_memorial_eletrico_v1_context(context)

        self.assertEqual(issues, [])

    def test_validate_memorial_eletrico_v1_context_returns_structured_errors(self) -> None:
        context = load_fixture()
        context["nao_inclusos"]["tem_itens"] = any(context["nao_inclusos"].values())
        del context["obra"]["nome"]

        with self.assertRaises(MemorialValidationError) as error_info:
            validate_memorial_eletrico_v1_context(context)

        self.assertTrue(error_info.exception.issues)
        first_issue = error_info.exception.issues[0]
        self.assertEqual(first_issue.path, "$.obra")
        self.assertIn("nome", first_issue.message)
        self.assertEqual(first_issue.validator, "required")

    def test_load_telecom_v1_schema_returns_expected_contract(self) -> None:
        schema = load_telecom_v1_schema()

        self.assertEqual(schema["title"], "MemorialTelecomContextV1")
        self.assertIn("obra", schema["required"])

    def test_validate_memorial_telecom_v1_context_accepts_valid_fixture(self) -> None:
        issues = validate_memorial_telecom_v1_context(load_telecom_fixture())

        self.assertEqual(issues, [])

    def test_validate_memorial_telecom_v1_context_rejects_missing_required_field(self) -> None:
        context = load_telecom_fixture()
        del context["obra"]["nome"]

        with self.assertRaises(MemorialValidationError) as error_info:
            validate_memorial_telecom_v1_context(context)

        first_issue = error_info.exception.issues[0]
        self.assertEqual(first_issue.path, "$.obra")
        self.assertIn("nome", first_issue.message)

    def test_validate_memorial_telecom_v1_context_rejects_additional_root_property(self) -> None:
        context = load_telecom_fixture()
        context["extra"] = True

        with self.assertRaises(MemorialValidationError) as error_info:
            validate_memorial_telecom_v1_context(context)

        first_issue = error_info.exception.issues[0]
        self.assertEqual(first_issue.path, "$")
        self.assertEqual(first_issue.validator, "additionalProperties")

    def test_load_gas_natural_v1_schema_returns_expected_contract(self) -> None:
        schema = load_gas_natural_v1_schema()

        self.assertEqual(schema["title"], "MemorialGasNaturalContextV1")
        self.assertIn("obra", schema["required"])
        self.assertIn("valvula", schema["required"])

    def test_validate_memorial_gas_natural_v1_context_accepts_valid_fixture(self) -> None:
        issues = validate_memorial_gas_natural_v1_context(load_gas_natural_fixture())

        self.assertEqual(issues, [])

    def test_validate_memorial_gas_natural_v1_context_accepts_original_diameter_notation(self) -> None:
        context = load_gas_natural_fixture()
        context["ramal"]["primario_diametro"] = '1 1/4"'

        issues = validate_memorial_gas_natural_v1_context(context)

        self.assertEqual(issues, [])

    def test_validate_memorial_gas_natural_v1_context_rejects_missing_required_field(self) -> None:
        context = load_gas_natural_fixture()
        del context["valvula"]["esfera_diametro"]

        with self.assertRaises(MemorialValidationError) as error_info:
            validate_memorial_gas_natural_v1_context(context)

        first_issue = error_info.exception.issues[0]
        self.assertEqual(first_issue.path, "$.valvula")
        self.assertIn("esfera_diametro", first_issue.message)

    def test_load_glp_v1_schema_returns_expected_contract(self) -> None:
        schema = load_glp_v1_schema()

        self.assertEqual(schema["title"], "MemorialGlpContextV1")
        self.assertIn("ramal", schema["required"])

    def test_validate_memorial_glp_v1_context_accepts_original_diameter_notation(self) -> None:
        context = load_glp_fixture()
        context["ramal"]["primario_diametro"] = '1 1/4"'

        issues = validate_memorial_glp_v1_context(context)

        self.assertEqual(issues, [])

    def test_load_glp_v2_schema_returns_expected_contract(self) -> None:
        schema = load_glp_v2_schema()
        self.assertEqual(schema["title"], "MemorialGlpContextV2")
        self.assertIn("pontos_utilizacao", schema["required"])

    def test_validate_memorial_glp_v2_context_accepts_minimal_valid(self) -> None:
        context = {
            "documento": {"data_atual": "01/01/2026"},
            "obra": {
                "numero_cadastro": "1",
                "construtora": "X",
                "nome": "Y",
                "localizacao": "Z",
                "tipo_edificacao": "residencial",
                "tipologia": "torre",
                "qtd_apartamentos": {"valor": 10, "confianca": "high"},
                "qtd_lojas": 0,
                "qtd_restaurantes": 0,
            },
            "tanques": {"quantidade": 1},
            "abastecimento": {"pavimento": "térreo"},
            "dimensionamento": {
                "qtd_fogao": 1,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 0,
                "qtd_outros": 0,
            },
            "pontos_utilizacao": {
                "fogao": 1,
                "churrasqueira": 0,
                "aquecedor": 0,
                "outros": 0,
                "total_extraido": None,
                "total_calculado": 1,
                "fontes_evidencia": [],
                "conflitos": [],
            },
            "diametros": {
                "tubulacao_principal": {
                    "valor": 1.25,
                    "unidade": "in",
                    "valor_formatado": '1 1/4"',
                },
                "valvula_esfera": {
                    "valor": 1.25,
                    "unidade": "in",
                    "valor_formatado": '1 1/4"',
                    "inferido": True,
                },
            },
            "ramal": {"primario_material": "aço carbono", "primario_pavimento": "térreo"},
            "numero": {"prancha": "01/01"},
            "teto_ou_piso": "piso",
            "context_version": "glp_v2",
            "template_version": "glp_v2",
        }
        validate_memorial_glp_v2_context(context)

    def test_validate_memorial_glp_v2_context_accepts_resolved_quantitative_conflict(self) -> None:
        context = {
            "documento": {"data_atual": "01/01/2026"},
            "obra": {
                "numero_cadastro": "1",
                "construtora": "X",
                "nome": "Y",
                "localizacao": "Z",
                "tipo_edificacao": "residencial",
                "tipologia": "torre",
                "qtd_apartamentos": {"valor": 29, "confianca": "medium"},
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
            "pontos_utilizacao": {
                "fogao": 35,
                "churrasqueira": 35,
                "aquecedor": 0,
                "outros": 0,
                "total_extraido": 70,
                "total_calculado": 70,
                "fontes_evidencia": [],
                "conflitos": [
                    {
                        "tipo": "glp_v2_points_total_mismatch",
                        "status": "resolved",
                        "valores_observados": [70, 34],
                        "fontes": ["total_extraido", "total_calculado"],
                        "mensagem": "Total extraido difere da soma por tipo.",
                        "valor_selecionado": 70,
                        "resolucao": "glp_v2_even_total_split",
                    }
                ],
            },
            "diametros": {
                "tubulacao_principal": {
                    "valor": 1.25,
                    "unidade": "in",
                    "valor_formatado": '1 1/4"',
                },
                "valvula_esfera": {
                    "valor": 1.25,
                    "unidade": "in",
                    "valor_formatado": '1 1/4"',
                    "inferido": True,
                },
            },
            "ramal": {"primario_material": "aço carbono", "primario_pavimento": "térreo"},
            "numero": {"prancha": "01/01"},
            "teto_ou_piso": "piso",
            "context_version": "glp_v2",
            "template_version": "glp_v2",
        }

        validate_memorial_glp_v2_context(context)

    def test_validate_memorial_glp_v2_context_rejects_bad_version(self) -> None:
        context = {
            "documento": {"data_atual": "01/01/2026"},
            "obra": {
                "numero_cadastro": "1",
                "construtora": "X",
                "nome": "Y",
                "localizacao": "Z",
                "tipo_edificacao": "residencial",
                "tipologia": "torre",
                "qtd_apartamentos": {"valor": 10},
                "qtd_lojas": 0,
                "qtd_restaurantes": 0,
            },
            "tanques": {"quantidade": 1},
            "abastecimento": {"pavimento": "térreo"},
            "dimensionamento": {
                "qtd_fogao": 1,
                "qtd_aquecedor": 0,
                "qtd_churrasqueira": 0,
                "qtd_outros": 0,
            },
            "pontos_utilizacao": {
                "fogao": 1,
                "churrasqueira": 0,
                "aquecedor": 0,
                "outros": 0,
                "total_extraido": None,
                "total_calculado": 1,
                "conflitos": [],
            },
            "diametros": {
                "tubulacao_principal": {"valor": 1.25, "unidade": "in", "valor_formatado": '1"'},
                "valvula_esfera": {"valor": 1.25, "unidade": "in", "valor_formatado": '1"'},
            },
            "ramal": {"primario_material": "aço", "primario_pavimento": "térreo"},
            "numero": {"prancha": "01/01"},
            "teto_ou_piso": "piso",
            "context_version": "wrong",
            "template_version": "glp_v2",
        }
        with self.assertRaises(MemorialValidationError):
            validate_memorial_glp_v2_context(context)

    def test_eletrico_allows_null_tipo_atendimento_when_not_parcial(self) -> None:
        context = load_fixture()
        context["nao_inclusos"]["tem_itens"] = any(context["nao_inclusos"].values())
        context["gerador"]["tem_gerador"] = True
        context["gerador"]["tipo_atendimento"] = None
        context["gerador"]["circuitos_atendidos"] = None
        validate_memorial_eletrico_v1_context(context)


if __name__ == "__main__":
    unittest.main()
