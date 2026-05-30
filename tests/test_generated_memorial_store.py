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
    filename_by_type = {
        "eletrico": "memorial_eletrico_v1.docx",
        "telecom": "memorial_telecom_v1.docx",
        "gas-natural": "memorial_gas_natural_v1.docx",
        "glp": "memorial_glp_v1.docx",
    }
    return {
        "id": memorial_id,
        "type": memorial_type,
        "project_name": "Memorial Telecom",
        "owner_user_id": "user-123",
        "created_by_name": "Usuario Teste",
        "status": "ready",
        "observations": "Observacao",
        "pdf_filenames": ["projeto.pdf"],
        "storage_bucket": "generated-memorials",
        "storage_path": f"{memorial_type}/{memorial_id}/{filename_by_type[memorial_type]}",
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
        self._table().update.return_value.eq.return_value.execute.return_value = _mock_response([])
        self._mock_client.storage.from_.return_value.create_signed_url.return_value = {
            "signedURL": "https://signed.example/download"
        }

        with NamedTemporaryFile(suffix=".docx") as temp_file:
            Path(temp_file.name).write_bytes(b"PK\x03\x04docx")
            memorial = store.create_generated_memorial(
                memorial_type="telecom",
                owner_user_id="user-123",
                created_by_name="Usuario Teste",
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
        self.assertEqual(inserted["owner_user_id"], "user-123")
        self.assertEqual(inserted["created_by_name"], "Usuario Teste")
        self.assertEqual(inserted["project_name"], "Memorial Telecom")
        self.assertEqual(inserted["status"], "processing")
        self.assertEqual(inserted["observations"], "Observacao")
        self.assertEqual(inserted["pdf_filenames"], ["projeto.pdf"])
        self.assertEqual(
            self._table().update.call_args[0][0],
            {"status": "ready", "updated_at": inserted["created_at"]},
        )
        self.assertEqual(memorial.download_url, "https://signed.example/download")

    def test_create_generated_memorial_marks_record_as_failed_when_upload_fails(self) -> None:
        self._table().insert.return_value.execute.return_value = _mock_response([])
        self._table().update.return_value.eq.return_value.execute.return_value = _mock_response([])
        self._mock_client.storage.from_.return_value.upload.side_effect = RuntimeError("storage offline")

        with NamedTemporaryFile(suffix=".docx") as temp_file:
            Path(temp_file.name).write_bytes(b"PK\x03\x04docx")

            with self.assertRaises(store.GeneratedMemorialStorageError):
                store.create_generated_memorial(
                    memorial_type="telecom",
                    owner_user_id="user-123",
                    created_by_name="Usuario Teste",
                    project_name="Memorial Telecom",
                    output_path=Path(temp_file.name),
                    pdf_filenames=["projeto.pdf"],
                    observations="Observacao",
                )

        inserted = self._table().insert.call_args[0][0]
        self.assertEqual(inserted["status"], "processing")
        self.assertEqual(
            self._table().update.call_args[0][0],
            {
                "status": "failed",
                "updated_at": inserted["created_at"],
            },
        )

    def test_list_generated_memorials_filters_by_type_when_provided(self) -> None:
        self._table().select.return_value.order.return_value.eq.return_value.execute.return_value = (
            _mock_response([_record(memorial_type="telecom")])
        )

        result = store.list_generated_memorials(memorial_type="telecom")

        self._table().select.assert_called_with("*")
        self._table().select.return_value.order.assert_called_with("created_at", desc=True)
        self._table().select.return_value.order.return_value.eq.assert_called_with("type", "telecom")
        self._mock_client.storage.from_.return_value.create_signed_url.assert_not_called()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].type, "telecom")
        self.assertEqual(result[0].download_url, "")

    def test_list_generated_memorials_survives_signed_url_transport_failure(self) -> None:
        self._table().select.return_value.order.return_value.execute.return_value = (
            _mock_response([_record(memorial_type="telecom")])
        )
        self._mock_client.storage.from_.return_value.create_signed_url.side_effect = (
            RuntimeError("Server disconnected")
        )

        result = store.list_generated_memorials()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].download_url, "")

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
            "telecom/abc-123/memorial_telecom_v1.docx",
            3600,
        )
        self.assertEqual(url, "https://signed.example/download")

    def test_create_signed_download_url_rejects_record_with_unexpected_storage_path(self) -> None:
        record = _record()
        record["storage_path"] = "../telecom/abc-123/memorial.docx"

        with self.assertRaises(store.GeneratedMemorialStorageError):
            store.create_signed_download_url(record)

        self._mock_client.storage.from_.return_value.create_signed_url.assert_not_called()

    def test_delete_generated_memorial_removes_storage_object_and_record(self) -> None:
        self._table().select.return_value.eq.return_value.execute.return_value = (
            _mock_response([_record()])
        )
        self._mock_client.storage.from_.return_value.remove.return_value = _mock_response([])
        self._table().delete.return_value.eq.return_value.execute.return_value = _mock_response([])

        deleted = store.delete_generated_memorial("abc-123")

        self.assertTrue(deleted)
        self._mock_client.storage.from_.assert_called_with("generated-memorials")
        self._mock_client.storage.from_.return_value.remove.assert_called_once_with(
            ["telecom/abc-123/memorial_telecom_v1.docx"]
        )
        self._table().delete.return_value.eq.assert_called_once_with("id", "abc-123")

    def test_delete_generated_memorial_returns_false_when_missing(self) -> None:
        self._table().select.return_value.eq.return_value.execute.return_value = _mock_response([])

        deleted = store.delete_generated_memorial("missing")

        self.assertFalse(deleted)
        self._mock_client.storage.from_.return_value.remove.assert_not_called()

    def test_delete_generated_memorial_rejects_record_with_unexpected_storage_path(self) -> None:
        record = _record()
        record["storage_path"] = "../../other-bucket/secret.docx"
        self._table().select.return_value.eq.return_value.execute.return_value = (
            _mock_response([record])
        )

        with self.assertRaises(store.GeneratedMemorialStorageError):
            store.delete_generated_memorial("abc-123")

        self._mock_client.storage.from_.return_value.remove.assert_not_called()
        self._table().delete.assert_not_called()

    def test_create_generated_memorial_persists_final_context_and_versions(self) -> None:
        self._mock_client.storage.from_.return_value.upload.return_value = _mock_response([])
        self._table().insert.return_value.execute.return_value = _mock_response([])
        self._table().update.return_value.eq.return_value.execute.return_value = _mock_response([])
        self._mock_client.storage.from_.return_value.create_signed_url.return_value = {
            "signedURL": "https://signed.example/download"
        }

        with NamedTemporaryFile(suffix=".docx", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        created = None
        try:
            temp_path.write_bytes(b"PK\x03\x04docx")
            created = store.create_generated_memorial(
                memorial_type="glp",
                owner_user_id="user-123",
                created_by_name="Usuario Teste",
                project_name="Memorial GLP",
                output_path=temp_path,
                pdf_filenames=["projeto.pdf"],
                observations=None,
                final_context={"obra": {"nome": "Edif Exemplo"}, "abastecimento": {"qtd_tanques": 1}},
                extraction_report={"filled": ["obra.nome"], "missing": [], "pending": []},
                conflicts=[{"type": "demo", "status": "resolved"}],
                context_version="glp_v1",
                template_version="glp_v1",
            )
        finally:
            temp_path.unlink(missing_ok=True)

        inserted = self._table().insert.call_args[0][0]
        self.assertEqual(inserted["context_version"], "glp_v1")
        self.assertEqual(inserted["template_version"], "glp_v1")
        self.assertEqual(inserted["final_context"]["obra"]["nome"], "Edif Exemplo")
        self.assertEqual(inserted["final_context"]["abastecimento"]["qtd_tanques"], 1)
        self.assertEqual(inserted["extraction_report"]["filled"], ["obra.nome"])
        self.assertEqual(inserted["conflicts"], [{"type": "demo", "status": "resolved"}])
        self.assertIsNotNone(created)
        self.assertIsNone(created.final_context)
        self.assertEqual(created.extraction_report["filled"], ["obra.nome"])
        self.assertEqual(created.conflicts, [{"type": "demo", "status": "resolved"}])

    def test_list_generated_memorials_omits_final_context_but_keeps_report_for_warnings(self) -> None:
        record = _record(memorial_type="glp")
        record["final_context"] = {"obra": {"nome": "X"}}
        record["extraction_report"] = {"filled": []}
        record["conflicts"] = [{"type": "demo"}]
        record["context_version"] = "glp_v1"
        record["template_version"] = "glp_v1"
        self._table().select.return_value.order.return_value.execute.return_value = (
            _mock_response([record])
        )

        result = store.list_generated_memorials()

        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0].final_context)
        self.assertEqual(result[0].extraction_report, {"filled": []})
        self.assertEqual(result[0].conflicts, [{"type": "demo"}])
        self.assertEqual(result[0].context_version, "glp_v1")
        self.assertEqual(result[0].template_version, "glp_v1")

    def test_get_generated_memorial_with_include_context_returns_final_context(self) -> None:
        record = _record(memorial_type="glp")
        record["final_context"] = {"obra": {"nome": "Edif Y"}}
        record["extraction_report"] = {"filled": ["obra.nome"]}
        record["conflicts"] = []
        record["context_version"] = "glp_v1"
        record["template_version"] = "glp_v1"
        self._table().select.return_value.eq.return_value.execute.return_value = (
            _mock_response([record])
        )
        self._mock_client.storage.from_.return_value.create_signed_url.return_value = {
            "signedURL": "https://signed.example/download"
        }

        result = store.get_generated_memorial("abc-123", include_context=True)

        self.assertIsNotNone(result)
        self.assertEqual(result.final_context, {"obra": {"nome": "Edif Y"}})
        self.assertEqual(result.extraction_report, {"filled": ["obra.nome"]})
        self.assertEqual(result.conflicts, [])
        self.assertEqual(result.context_version, "glp_v1")

    def test_get_generated_memorial_default_omits_context(self) -> None:
        record = _record(memorial_type="glp")
        record["final_context"] = {"obra": {"nome": "Edif Y"}}
        record["extraction_report"] = {"filled": ["obra.nome"]}
        record["conflicts"] = []
        record["context_version"] = "glp_v1"
        record["template_version"] = "glp_v1"
        self._table().select.return_value.eq.return_value.execute.return_value = (
            _mock_response([record])
        )
        self._mock_client.storage.from_.return_value.create_signed_url.return_value = {
            "signedURL": "https://signed.example/download"
        }

        result = store.get_generated_memorial("abc-123")

        self.assertIsNotNone(result)
        self.assertIsNone(result.final_context)
        self.assertEqual(result.extraction_report, {"filled": ["obra.nome"]})
        self.assertEqual(result.conflicts, [])
        self.assertEqual(result.context_version, "glp_v1")


if __name__ == "__main__":
    unittest.main()
