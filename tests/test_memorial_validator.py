from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.services.memorial_validator import (
    MemorialValidationError,
    load_eletrico_v1_schema,
    validate_memorial_eletrico_v1_context,
)


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "eletrico_sem_subestacao.json"


def load_fixture() -> dict:
    with FIXTURE_PATH.open("r", encoding="utf-8") as file:
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


if __name__ == "__main__":
    unittest.main()
