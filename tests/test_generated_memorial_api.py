from __future__ import annotations

import asyncio
import unittest
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from docx import Document
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile
from starlette.middleware.cors import CORSMiddleware

import app.api.routes as routes
from app.main import app
from app.schemas.generated_memorial import GeneratedMemorialResponse
from app.services.generated_memorial_store import (
    GeneratedMemorialArtifactNotFoundError,
    GeneratedMemorialStorageError,
)


def _memorial(memorial_id: str = "abc-123", memorial_type: str = "telecom") -> GeneratedMemorialResponse:
    now = datetime.now(tz=timezone.utc)
    return GeneratedMemorialResponse(
        id=memorial_id,
        type=memorial_type,
        project_name="Memorial Telecom",
        status="ready",
        observations="Observacao",
        pdf_filenames=["projeto.pdf"],
        created_at=now,
        updated_at=now,
        download_url="https://signed.example/download",
    )


class GeneratedMemorialApiTests(unittest.TestCase):
    def test_cors_allows_local_vite_frontend_origin(self) -> None:
        cors_middleware = next(
            middleware
            for middleware in app.user_middleware
            if middleware.cls is CORSMiddleware
        )
        self.assertIn("http://localhost:5173", cors_middleware.kwargs["allow_origins"])
        self.assertIn("http://127.0.0.1:5173", cors_middleware.kwargs["allow_origins"])

    @patch("app.api.routes.create_generated_memorial")
    @patch(
        "app.api.routes.generate_memorial_telecom_v1_from_uploaded_files",
        new_callable=AsyncMock,
    )
    def test_post_persisted_telecom_from_files_returns_memorial_metadata(
        self,
        pipeline_mock,
        create_mock,
    ) -> None:
        async def pipeline_side_effect(_files, output_path: Path):
            document = Document()
            document.add_paragraph("Memorial telecom gerado.")
            document.save(output_path)

        pipeline_mock.side_effect = pipeline_side_effect
        create_mock.return_value = _memorial()

        files = [UploadFile(filename="projeto.pdf", file=BytesIO(b"%PDF-1.4 teste"))]
        response = asyncio.run(
            routes.create_persisted_memorial_from_files(
                "telecom",
                MagicMock(),
                files,
                "Observacao",
            )
        )

        self.assertEqual(response.id, "abc-123")
        self.assertEqual(response.type, "telecom")
        self.assertEqual(response.project_name, "Memorial Telecom")
        self.assertEqual(response.pdf_filenames, ["projeto.pdf"])
        self.assertEqual(response.download_url, "https://signed.example/download")
        create_mock.assert_called_once()
        self.assertEqual(create_mock.call_args.kwargs["memorial_type"], "telecom")
        self.assertEqual(create_mock.call_args.kwargs["observations"], "Observacao")

    @patch("app.api.routes.list_generated_memorials")
    def test_get_memoriais_lists_persisted_memorials(self, list_mock) -> None:
        list_mock.return_value = [_memorial()]

        response = routes.list_persisted_memorials(type="telecom")

        self.assertEqual(len(response.memorials), 1)
        self.assertEqual(response.memorials[0].type, "telecom")
        list_mock.assert_called_once_with("telecom")

    @patch("app.api.routes.get_generated_memorial")
    def test_get_memorial_returns_404_for_unknown_id(self, get_mock) -> None:
        get_mock.return_value = None

        response = routes.get_persisted_memorial("missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.body.decode("utf-8"), '{"detail":"Memorial não encontrado."}')

    @patch("app.api.routes.get_generated_memorial")
    def test_get_memorial_returns_detail(self, get_mock) -> None:
        get_mock.return_value = _memorial()

        response = routes.get_persisted_memorial("abc-123")

        self.assertEqual(response.id, "abc-123")

    @patch("app.api.routes.create_signed_download_url")
    @patch("app.api.routes.get_generated_memorial_record")
    def test_get_memorial_download_returns_signed_url(self, get_record_mock, signed_url_mock) -> None:
        get_record_mock.return_value = {
            "id": "abc-123",
            "type": "telecom",
            "storage_bucket": "generated-memorials",
            "storage_path": "telecom/abc-123/memorial_telecom_v1.docx",
        }
        signed_url_mock.return_value = "https://signed.example/download"

        request = MagicMock()
        request.state.request_id = "req-123"
        request.method = "GET"
        request.url.path = "/api/v1/memoriais/abc-123/download"

        response = routes.get_persisted_memorial_download("abc-123", request)

        self.assertEqual(response.download_url, "https://signed.example/download")

    @patch("app.api.routes.create_signed_download_url")
    @patch("app.api.routes.get_generated_memorial_record")
    def test_get_memorial_download_returns_404_when_artifact_is_missing(
        self,
        get_record_mock,
        signed_url_mock,
    ) -> None:
        get_record_mock.return_value = {
            "id": "abc-123",
            "type": "telecom",
            "storage_bucket": "generated-memorials",
            "storage_path": "telecom/abc-123/memorial_telecom_v1.docx",
        }
        signed_url_mock.side_effect = GeneratedMemorialArtifactNotFoundError("missing")

        request = MagicMock()
        request.state.request_id = "req-123"
        request.method = "GET"
        request.url.path = "/api/v1/memoriais/abc-123/download"

        response = routes.get_persisted_memorial_download("abc-123", request)

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 404)
        self.assertIn("não está mais disponível", response.body.decode("utf-8"))
        self.assertNotIn("telecom/abc-123", response.body.decode("utf-8"))

    @patch("app.api.routes.create_signed_download_url")
    @patch("app.api.routes.get_generated_memorial_record")
    def test_get_memorial_download_returns_safe_503_for_storage_failure(
        self,
        get_record_mock,
        signed_url_mock,
    ) -> None:
        get_record_mock.return_value = {
            "id": "abc-123",
            "type": "telecom",
            "storage_bucket": "generated-memorials",
            "storage_path": "telecom/abc-123/memorial_telecom_v1.docx",
        }
        signed_url_mock.side_effect = GeneratedMemorialStorageError(
            "raw internal storage path /srv/private"
        )

        request = MagicMock()
        request.state.request_id = "req-123"
        request.method = "GET"
        request.url.path = "/api/v1/memoriais/abc-123/download"

        response = routes.get_persisted_memorial_download("abc-123", request)

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 503)
        body = response.body.decode("utf-8")
        self.assertIn("Armazenamento do memorial indisponível.", body)
        self.assertNotIn("/srv/private", body)

    @patch("app.api.routes.delete_generated_memorial")
    def test_delete_memorial_returns_204_when_deleted(self, delete_mock) -> None:
        delete_mock.return_value = True

        response = routes.delete_persisted_memorial("abc-123", MagicMock())

        self.assertEqual(response.status_code, 204)
        delete_mock.assert_called_once_with("abc-123")

    @patch("app.api.routes.delete_generated_memorial")
    def test_delete_memorial_returns_404_when_missing(self, delete_mock) -> None:
        delete_mock.return_value = False

        response = routes.delete_persisted_memorial("missing", MagicMock())

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.body.decode("utf-8"), '{"detail":"Memorial não encontrado."}')

    @patch("app.api.routes.delete_generated_memorial")
    def test_delete_memorial_returns_safe_503_for_storage_failure(self, delete_mock) -> None:
        delete_mock.side_effect = GeneratedMemorialStorageError("leaked path /srv/private")

        request = MagicMock()
        request.state.request_id = "req-123"
        request.method = "DELETE"
        request.url.path = "/api/v1/memoriais/abc-123"

        response = routes.delete_persisted_memorial("abc-123", request)

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 503)
        body = response.body.decode("utf-8")
        self.assertIn("Armazenamento do memorial indisponível.", body)
        self.assertNotIn("/srv/private", body)


if __name__ == "__main__":
    unittest.main()
