from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, patch

from docx import Document
from fastapi.testclient import TestClient

from app.main import app
from app.services.memorial_validator import MemorialValidationError, ValidationIssue
from app.services.pipeline import PipelineResult


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

    def test_post_memorial_eletrico_upload_returns_metadata_for_valid_files(self) -> None:
        files = [
            ("files", ("projeto.pdf", b"%PDF-1.4 teste", "application/pdf")),
            (
                "files",
                (
                    "memorial.docx",
                    b"PK\x03\x04conteudo",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            ),
        ]

        response = self.client.post("/api/v1/memoriais/eletrico/upload", files=files)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["files"]), 2)
        self.assertNotIn("request_dir", body)
        self.assertNotIn("saved_path", body["files"][0])
        self.assertEqual(body["files"][0]["extension"], ".pdf")
        self.assertEqual(body["files"][1]["extension"], ".docx")
        self.assertEqual(body["files"][0]["filename"], "projeto.pdf")

    def test_post_memorial_eletrico_upload_returns_400_for_invalid_extension(self) -> None:
        files = [
            (
                "files",
                (
                    "projeto.txt",
                    b"conteudo",
                    "text/plain",
                ),
            )
        ]

        response = self.client.post("/api/v1/memoriais/eletrico/upload", files=files)

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("Extensao nao suportada", body["detail"])

    def test_post_memorial_eletrico_upload_returns_400_for_empty_list(self) -> None:
        response = self.client.post("/api/v1/memoriais/eletrico/upload", files=[])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Envie ao menos um arquivo PDF ou DOCX.",
        )

    @patch(
        "app.api.routes.generate_memorial_eletrico_v1_from_uploaded_files",
        new_callable=AsyncMock,
    )
    def test_post_memorial_eletrico_from_files_returns_docx_for_valid_files(
        self,
        pipeline_mock,
    ) -> None:
        async def pipeline_side_effect(_files, output_path: Path) -> PipelineResult:
            document = Document()
            document.add_paragraph("Memorial gerado a partir de arquivos.")
            document.save(output_path)
            return PipelineResult(
                context={"obra": {"nome": "Edificio Exemplo"}},
                output_path=output_path,
            )

        pipeline_mock.side_effect = pipeline_side_effect

        with TemporaryDirectory() as temp_dir:
            files = [
                (
                    "files",
                    (
                        "projeto.docx",
                        b"PK\x03\x04conteudo",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                )
            ]

            response = self.client.post(
                "/api/v1/memoriais/eletrico/from-files",
                files=files,
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.headers["content-type"],
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            self.assertTrue(response.content.startswith(b"PK"))

        pipeline_mock.assert_awaited_once()

    def test_post_memorial_eletrico_from_files_returns_400_for_invalid_extension(self) -> None:
        files = [
            (
                "files",
                (
                    "projeto.txt",
                    b"conteudo",
                    "text/plain",
                ),
            )
        ]

        response = self.client.post(
            "/api/v1/memoriais/eletrico/from-files",
            files=files,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Extensao nao suportada", response.json()["detail"])

    @patch(
        "app.api.routes.generate_memorial_eletrico_v1_from_uploaded_files",
        new_callable=AsyncMock,
    )
    def test_post_memorial_eletrico_from_files_returns_400_for_validation_error(
        self,
        pipeline_mock,
    ) -> None:
        pipeline_mock.side_effect = MemorialValidationError(
            [
                ValidationIssue(
                    path="$",
                    message="'documento' is a required property",
                    validator="required",
                )
            ]
        )
        files = [
            (
                "files",
                (
                    "projeto.docx",
                    b"PK\x03\x04conteudo",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            )
        ]

        response = self.client.post(
            "/api/v1/memoriais/eletrico/from-files",
            files=files,
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["detail"], "Payload invalido para o memorial eletrico v1.")
        self.assertTrue(body["errors"])
        self.assertEqual(body["errors"][0]["path"], "$")


if __name__ == "__main__":
    unittest.main()
