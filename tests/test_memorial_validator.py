from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.services.memorial_validator import (
    MemorialValidationError,
    load_eletrico_v1_schema,
    load_gas_natural_v1_schema,
    load_telecom_v1_schema,
    validate_memorial_eletrico_v1_context,
    validate_memorial_gas_natural_v1_context,
    validate_memorial_telecom_v1_context,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "eletrico_sem_subestacao.json"
TELECOM_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "telecom_base.json"
GAS_NATURAL_FIXTURE_PATH = ROOT / "tests" / "fixtures" / "gas_natural_base.json"


def load_fixture() -> dict:
    with FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_telecom_fixture() -> dict:
    with TELECOM_FIXTURE_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_gas_natural_fixture() -> dict:
    with GAS_NATURAL_FIXTURE_PATH.open("r", encoding="utf-8") as file:
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

    def test_validate_memorial_gas_natural_v1_context_rejects_missing_required_field(self) -> None:
        context = load_gas_natural_fixture()
        del context["valvula"]["esfera_diametro"]

        with self.assertRaises(MemorialValidationError) as error_info:
            validate_memorial_gas_natural_v1_context(context)

        first_issue = error_info.exception.issues[0]
        self.assertEqual(first_issue.path, "$.valvula")
        self.assertIn("esfera_diametro", first_issue.message)


if __name__ == "__main__":
    unittest.main()
