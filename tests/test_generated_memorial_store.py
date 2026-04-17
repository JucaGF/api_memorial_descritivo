from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch

import app.services.generated_memorial_store as store


def _mock_response(data: list | dict | None = None) -> MagicMock:
    response = MagicMock()
    response.data = data
    return response


def _record(memorial_id: str = "abc-123", memorial_type: str = "telecom") -> dict:
    now = datetime.now(tz=timezone.utc).isoformat()
    return {
        "id": memorial_id,
        "type": memorial_type,
        "project_name": "Memorial Telecom",
        "status": "ready",
        "observations": "Observacao",
        "pdf_filenames": ["projeto.pdf"],
        "storage_bucket": "generated-memorials",
        "storage_path": f"{memorial_type}/{memorial_id}/memorial.docx",
        "created_at": now,
        "updated_at": now,
    }


class GeneratedMemorialStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        store._client_instance = None
        self._mock_client = MagicMock()
        self._patcher = patch(
            "app.services.generated_memorial_store._client",
            return_value=self._mock_client,
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.addCleanup(setattr, store, "_client_instance", None)

    def _table(self) -> MagicMock:
        return self._mock_client.table.return_value

    def test_create_generated_memorial_uploads_docx_and_inserts_metadata(self) -> None:
        self._mock_client.storage.from_.return_value.upload.return_value = _mock_response([])
        self._table().insert.return_value.execute.return_value = _mock_response([])
        self._mock_client.storage.from_.return_value.create_signed_url.return_value = {
            "signedURL": "https://signed.example/download"
        }

        with NamedTemporaryFile(suffix=".docx") as temp_file:
            Path(temp_file.name).write_bytes(b"PK\x03\x04docx")
            memorial = store.create_generated_memorial(
                memorial_type="telecom",
                project_name="Memorial Telecom",
                output_path=Path(temp_file.name),
                pdf_filenames=["projeto.pdf"],
                observations="Observacao",
            )

        uploaded_path = self._mock_client.storage.from_.return_value.upload.call_args[0][0]
        self.assertTrue(uploaded_path.startswith("telecom/"))
        self.assertTrue(uploaded_path.endswith("/memorial_telecom_v1.docx"))
        inserted = self._table().insert.call_args[0][0]
        self.assertEqual(inserted["type"], "telecom")
        self.assertEqual(inserted["project_name"], "Memorial Telecom")
        self.assertEqual(inserted["status"], "ready")
        self.assertEqual(inserted["observations"], "Observacao")
        self.assertEqual(inserted["pdf_filenames"], ["projeto.pdf"])
        self.assertEqual(memorial.download_url, "https://signed.example/download")

    def test_list_generated_memorials_filters_by_type_when_provided(self) -> None:
        self._table().select.return_value.order.return_value.eq.return_value.execute.return_value = (
            _mock_response([_record(memorial_type="telecom")])
        )
        self._mock_client.storage.from_.return_value.create_signed_url.return_value = {
            "signedURL": "https://signed.example/download"
        }

        result = store.list_generated_memorials(memorial_type="telecom")

        self._table().select.assert_called_with("*")
        self._table().select.return_value.order.assert_called_with("created_at", desc=True)
        self._table().select.return_value.order.return_value.eq.assert_called_with("type", "telecom")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, "telecom")

    def test_get_generated_memorial_returns_none_when_missing(self) -> None:
        self._table().select.return_value.eq.return_value.execute.return_value = _mock_response([])

        result = store.get_generated_memorial("missing")

        self.assertIsNone(result)

    def test_create_signed_download_url_uses_record_storage_location(self) -> None:
        self._mock_client.storage.from_.return_value.create_signed_url.return_value = {
            "signedURL": "https://signed.example/download"
        }

        url = store.create_signed_download_url(_record())

        self._mock_client.storage.from_.assert_called_with("generated-memorials")
        self._mock_client.storage.from_.return_value.create_signed_url.assert_called_with(
            "telecom/abc-123/memorial.docx",
            3600,
        )
        self.assertEqual(url, "https://signed.example/download")


if __name__ == "__main__":
    unittest.main()
