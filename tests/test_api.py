from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone

from docx import Document
from fastapi.testclient import TestClient

from app.main import app
from app.services.extraction_mapper import ExtractionReport, MappingResult
from app.services.memorial_validator import MemorialValidationError, ValidationIssue
from app.services.pipeline import PipelineResult
from app.services.session_store import ReviewSession


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

    def test_post_memorial_telecom_returns_docx_for_valid_payload(self) -> None:
        payload = load_fixture("telecom_base.json")

        response = self.client.post("/api/v1/memoriais/telecom", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertTrue(
            response.headers["content-disposition"].startswith("attachment;")
        )
        self.assertTrue(response.content.startswith(b"PK"))

    def test_post_memorial_telecom_returns_400_for_invalid_payload(self) -> None:
        payload = load_fixture("telecom_base.json")
        del payload["obra"]["nome"]

        response = self.client.post("/api/v1/memoriais/telecom", json=payload)

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(
            body["detail"],
            "Payload invalido para o memorial telecom v1.",
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

    def test_post_memorial_telecom_upload_returns_metadata_for_valid_files(self) -> None:
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

        response = self.client.post("/api/v1/memoriais/telecom/upload", files=files)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["files"]), 2)
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

    @patch(
        "app.api.routes.generate_memorial_telecom_v1_from_uploaded_files",
        new_callable=AsyncMock,
    )
    def test_post_memorial_telecom_from_files_returns_docx_for_valid_files(
        self,
        pipeline_mock,
    ) -> None:
        async def pipeline_side_effect(_files, output_path: Path) -> PipelineResult:
            document = Document()
            document.add_paragraph("Memorial telecom gerado a partir de arquivos.")
            document.save(output_path)
            return PipelineResult(
                context={"obra": {"nome": "Edificio Exemplo"}},
                output_path=output_path,
            )

        pipeline_mock.side_effect = pipeline_side_effect

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
            "/api/v1/memoriais/telecom/from-files",
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

    @patch(
        "app.api.routes.generate_memorial_telecom_v1_from_uploaded_files",
        new_callable=AsyncMock,
    )
    def test_post_memorial_telecom_from_files_returns_400_for_validation_error(
        self,
        pipeline_mock,
    ) -> None:
        pipeline_mock.side_effect = MemorialValidationError(
            [
                ValidationIssue(
                    path="$.obra",
                    message="'tipologia' is a required property",
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
            "/api/v1/memoriais/telecom/from-files",
            files=files,
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["detail"], "Payload invalido para o memorial telecom v1.")
        self.assertTrue(body["errors"])
        self.assertEqual(body["errors"][0]["path"], "$.obra")


def _build_pending_session(session_id: str) -> ReviewSession:
    from datetime import datetime, timedelta, timezone
    now = datetime.now(tz=timezone.utc)
    return ReviewSession(
        session_id=session_id,
        status="pending_review",
        created_at=now.isoformat(),
        expires_at=(now + timedelta(hours=24)).isoformat(),
        partial_context={"obra": {"nome": "Makai", "construtora": "MGA LTDA"}},
        extraction_report={"filled": ["obra.nome"], "missing": ["obra.tipo_edificacao"], "pending": [], "evidence": {}},
        corrections={},
    )


class ReviewSessionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    @patch("app.api.routes._process_review_session")
    @patch("app.api.routes.create_session", return_value="test-session-id")
    @patch("app.api.routes.ingest_uploaded_files", new_callable=AsyncMock)
    def test_post_sessoes_returns_202_with_session_id(
        self, ingest_mock, create_mock, process_mock
    ) -> None:
        ingest_mock.return_value = MagicMock(files=[])

        files = [("files", ("projeto.pdf", b"%PDF-1.4 teste", "application/pdf"))]
        response = self.client.post("/api/v1/memoriais/eletrico/sessoes", files=files)

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["session_id"], "test-session-id")
        self.assertEqual(body["status"], "processing")

    @patch("app.api.routes.cleanup_ingestion_result")
    @patch("app.api.routes.create_session", side_effect=RuntimeError("db down"))
    @patch("app.api.routes.ingest_uploaded_files", new_callable=AsyncMock)
    def test_post_sessoes_cleans_temp_files_when_create_session_fails(
        self,
        ingest_mock,
        create_mock,
        cleanup_mock,
    ) -> None:
        ingestion_result = MagicMock(files=[])
        ingest_mock.return_value = ingestion_result
        files = [("files", ("projeto.pdf", b"%PDF-1.4 teste", "application/pdf"))]

        with self.assertRaises(RuntimeError):
            self.client.post("/api/v1/memoriais/eletrico/sessoes", files=files)

        cleanup_mock.assert_called_once_with(ingestion_result)

    @patch("app.api.routes.delete_session")
    @patch("app.api.routes.cleanup_ingestion_result")
    @patch("app.api.routes.create_session", return_value="test-session-id")
    @patch("app.api.routes.ingest_uploaded_files", new_callable=AsyncMock)
    def test_post_sessoes_cleans_temp_files_and_deletes_session_when_add_task_fails(
        self,
        ingest_mock,
        create_mock,
        cleanup_mock,
        delete_mock,
    ) -> None:
        ingestion_result = MagicMock(files=[])
        ingest_mock.return_value = ingestion_result
        files = [("files", ("projeto.pdf", b"%PDF-1.4 teste", "application/pdf"))]

        with patch("app.api.routes.BackgroundTasks.add_task", side_effect=RuntimeError("task queue down")):
            with self.assertRaises(RuntimeError):
                self.client.post("/api/v1/memoriais/eletrico/sessoes", files=files)

        cleanup_mock.assert_called_once_with(ingestion_result)
        delete_mock.assert_called_once_with("test-session-id")

    @patch("app.api.routes.load_session", return_value=None)
    def test_get_sessoes_returns_404_for_unknown_id(self, _) -> None:
        response = self.client.get("/api/v1/memoriais/eletrico/sessoes/nao-existe")

        self.assertEqual(response.status_code, 404)
        self.assertIn("não encontrada", response.json()["detail"])

    def test_get_sessoes_returns_404_for_expired_session_in_filesystem_store(self) -> None:
        from app.services import session_store

        with TemporaryDirectory() as temp_dir:
            session_id = "expired-session"
            expired_session = ReviewSession(
                session_id=session_id,
                status="pending_review",
                created_at=(datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat(),
                expires_at=(datetime.now(tz=timezone.utc) - timedelta(minutes=1)).isoformat(),
            )
            session_file = Path(temp_dir) / f"{session_id}.json"
            with patch("app.services.session_store._sessions_dir", return_value=Path(temp_dir)):
                session_store.save_session(expired_session)

                response = self.client.get(f"/api/v1/memoriais/eletrico/sessoes/{session_id}")

            self.assertEqual(response.status_code, 404)
            self.assertFalse(session_file.exists())

    @patch("app.api.routes.load_session")
    def test_get_sessoes_returns_full_session_state(self, load_mock) -> None:
        session = _build_pending_session("abc-123")
        load_mock.return_value = session

        response = self.client.get("/api/v1/memoriais/eletrico/sessoes/abc-123")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["session_id"], "abc-123")
        self.assertEqual(body["status"], "pending_review")
        self.assertIn("partial_context", body)
        self.assertIn("extraction_report", body)
        self.assertIn("filled", body["extraction_report"])
        self.assertIn("missing", body["extraction_report"])
        self.assertIn("pending", body["extraction_report"])
        self.assertIn("evidence", body["extraction_report"])

    @patch("app.api.routes.load_session")
    def test_get_sessoes_preserves_typed_extraction_report_shape_with_evidence(self, load_mock) -> None:
        session = _build_pending_session("abc-123")
        session.extraction_report = {
            "filled": ["obra.nome"],
            "missing": ["obra.tipo_edificacao"],
            "pending": [],
            "evidence": {
                "obra.nome": {
                    "value": "Makai",
                    "rule": "carimbo_line_before_company",
                    "evidence": "'MAKAI' — linha anterior a 'MGA CONSTRUÇÕES'",
                    "confidence": "high",
                }
            },
        }
        load_mock.return_value = session

        response = self.client.get("/api/v1/memoriais/eletrico/sessoes/abc-123")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["extraction_report"]["filled"], ["obra.nome"])
        self.assertEqual(
            body["extraction_report"]["evidence"]["obra.nome"]["rule"],
            "carimbo_line_before_company",
        )
        self.assertEqual(
            body["extraction_report"]["evidence"]["obra.nome"]["confidence"],
            "high",
        )

    @patch("app.api.routes.load_session")
    def test_get_sessoes_accepts_empty_extraction_report_for_processing_compatibility(
        self,
        load_mock,
    ) -> None:
        now = datetime.now(tz=timezone.utc)
        load_mock.return_value = ReviewSession(
            session_id="abc-123",
            status="processing",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(hours=24)).isoformat(),
            extraction_report={},
        )

        response = self.client.get("/api/v1/memoriais/eletrico/sessoes/abc-123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["extraction_report"], {})

    @patch("app.api.routes.load_session")
    def test_patch_contexto_returns_409_when_still_processing(self, load_mock) -> None:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(tz=timezone.utc)
        load_mock.return_value = ReviewSession(
            session_id="abc-123",
            status="processing",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(hours=24)).isoformat(),
        )

        response = self.client.patch(
            "/api/v1/memoriais/eletrico/sessoes/abc-123/contexto",
            json={"corrections": {"obra": {"nome": "Novo Nome"}}},
        )

        self.assertEqual(response.status_code, 409)

    @patch("app.api.routes.update_session")
    @patch("app.api.routes.load_session")
    def test_patch_contexto_accumulates_corrections(
        self, load_mock, update_mock
    ) -> None:
        session = _build_pending_session("abc-123")
        session_with_existing = ReviewSession(
            **{**session.__dict__, "corrections": {"obra": {"tipo_edificacao": "Residencial"}}}
        )
        load_mock.return_value = session_with_existing

        updated_session = ReviewSession(
            **{**session_with_existing.__dict__,
               "corrections": {"obra": {"tipo_edificacao": "Residencial", "tipologia": "Vertical"}}}
        )
        update_mock.return_value = updated_session

        response = self.client.patch(
            "/api/v1/memoriais/eletrico/sessoes/abc-123/contexto",
            json={"corrections": {"obra": {"tipologia": "Vertical"}}},
        )

        self.assertEqual(response.status_code, 200)
        update_mock.assert_called_once()
        merged = update_mock.call_args[1]["corrections"]
        self.assertEqual(merged["obra"]["tipo_edificacao"], "Residencial")
        self.assertEqual(merged["obra"]["tipologia"], "Vertical")

    @patch("app.api.routes.load_session", return_value=None)
    def test_post_gerar_returns_404_for_unknown_session(self, _) -> None:
        response = self.client.post("/api/v1/memoriais/eletrico/sessoes/nao-existe/gerar")

        self.assertEqual(response.status_code, 404)

    @patch("app.api.routes.load_session")
    def test_post_gerar_returns_409_when_session_still_processing(self, load_mock) -> None:
        from datetime import datetime, timedelta, timezone
        now = datetime.now(tz=timezone.utc)
        load_mock.return_value = ReviewSession(
            session_id="abc-123",
            status="processing",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(hours=24)).isoformat(),
        )

        response = self.client.post("/api/v1/memoriais/eletrico/sessoes/abc-123/gerar")

        self.assertEqual(response.status_code, 409)

    @patch("app.api.routes.delete_session")
    @patch("app.api.routes.generate_memorial_eletrico_v1")
    @patch("app.api.routes.load_session")
    def test_post_gerar_returns_docx_on_success(
        self, load_mock, generate_mock, delete_mock
    ) -> None:
        session = _build_pending_session("abc-123")
        load_mock.return_value = session

        def generate_side_effect(context, output_path):
            doc = Document()
            doc.add_paragraph("Memorial gerado.")
            doc.save(output_path)
            return PipelineResult(context=context, output_path=output_path)

        generate_mock.side_effect = generate_side_effect

        response = self.client.post("/api/v1/memoriais/eletrico/sessoes/abc-123/gerar")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        self.assertTrue(response.content.startswith(b"PK"))

    @patch("app.api.routes.generate_memorial_eletrico_v1")
    @patch("app.api.routes.load_session")
    def test_post_gerar_returns_400_on_validation_error(
        self, load_mock, generate_mock
    ) -> None:
        session = _build_pending_session("abc-123")
        load_mock.return_value = session
        generate_mock.side_effect = MemorialValidationError(
            [ValidationIssue(path="$.obra", message="'tipo_edificacao' is a required property", validator="required")]
        )

        response = self.client.post("/api/v1/memoriais/eletrico/sessoes/abc-123/gerar")

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["detail"], "Payload invalido para o memorial eletrico v1.")
        self.assertTrue(body["errors"])


if __name__ == "__main__":
    unittest.main()
