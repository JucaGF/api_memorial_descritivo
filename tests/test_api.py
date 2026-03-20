from __future__ import annotations

import json
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "tests" / "fixtures"


def load_fixture(filename: str) -> dict:
    with (FIXTURES_DIR / filename).open("r", encoding="utf-8") as file:
        return json.load(file)


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_post_memorial_eletrico_returns_docx_for_valid_payload(self) -> None:
        payload = load_fixture("eletrico_com_subestacao.json")

        response = self.client.post("/api/v1/memoriais/eletrico", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertTrue(
            response.headers["content-disposition"].startswith("attachment;")
        )
        self.assertTrue(response.content.startswith(b"PK"))

    def test_post_memorial_eletrico_returns_400_for_invalid_payload(self) -> None:
        payload = load_fixture("eletrico_sem_subestacao.json")
        del payload["obra"]["nome"]

        response = self.client.post("/api/v1/memoriais/eletrico", json=payload)

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(
            body["detail"],
            "Payload invalido para o memorial eletrico v1.",
        )
        self.assertTrue(body["errors"])
        self.assertEqual(body["errors"][0]["path"], "$.obra")
        self.assertIn("nome", body["errors"][0]["message"])


if __name__ == "__main__":
    unittest.main()
