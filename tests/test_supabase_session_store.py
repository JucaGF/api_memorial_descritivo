from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import app.services.supabase_session_store as store
from app.services.session_store import ReviewSession


def _mock_response(data: list) -> MagicMock:
    response = MagicMock()
    response.data = data
    return response


def _session_data(session_id: str = "test-id", status: str = "processing") -> dict:
    now = datetime.now(tz=timezone.utc)
    return {
        "session_id": session_id,
        "status": status,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=24)).isoformat(),
        "partial_context": {},
        "extraction_report": {},
        "corrections": {},
        "error": None,
    }


class SupabaseSessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        store._client_instance = None
        self._mock_client = MagicMock()
        self._patcher = patch(
            "app.services.supabase_session_store._client",
            return_value=self._mock_client,
        )
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()
        store._client_instance = None

    def _table(self) -> MagicMock:
        return self._mock_client.table.return_value

    # ── create_session ────────────────────────────────────────────────────────

    def test_create_session_inserts_record_and_returns_uuid(self) -> None:
        self._table().insert.return_value.execute.return_value = _mock_response([])

        session_id = store.create_session()

        self._mock_client.table.assert_called_with("review_sessions")
        self._table().insert.assert_called_once()
        inserted = self._table().insert.call_args[0][0]
        self.assertEqual(inserted["session_id"], session_id)
        self.assertEqual(inserted["status"], "processing")
        self.assertEqual(len(session_id), 36)

    def test_create_session_sets_expires_at_24h_ahead(self) -> None:
        self._table().insert.return_value.execute.return_value = _mock_response([])

        before = datetime.now(tz=timezone.utc)
        store.create_session()

        inserted = self._table().insert.call_args[0][0]
        expires_at = datetime.fromisoformat(inserted["expires_at"])
        created_at = datetime.fromisoformat(inserted["created_at"])
        delta = expires_at - created_at
        self.assertAlmostEqual(delta.total_seconds(), 86400, delta=5)

    # ── load_session ──────────────────────────────────────────────────────────

    def test_load_session_returns_session_when_found(self) -> None:
        data = _session_data("abc-123", "pending_review")
        self._table().select.return_value.eq.return_value.execute.return_value = _mock_response([data])

        session = store.load_session("abc-123")

        self.assertIsNotNone(session)
        self.assertIsInstance(session, ReviewSession)
        self.assertEqual(session.session_id, "abc-123")
        self.assertEqual(session.status, "pending_review")

    def test_load_session_returns_none_when_not_found(self) -> None:
        self._table().select.return_value.eq.return_value.execute.return_value = _mock_response([])

        result = store.load_session("nao-existe")

        self.assertIsNone(result)

    def test_load_session_queries_correct_table_and_field(self) -> None:
        self._table().select.return_value.eq.return_value.execute.return_value = _mock_response([])

        store.load_session("abc-123")

        self._mock_client.table.assert_called_with("review_sessions")
        self._table().select.assert_called_with("*")
        self._table().select.return_value.eq.assert_called_with("session_id", "abc-123")

    # ── update_session ────────────────────────────────────────────────────────

    def test_update_session_applies_kwargs_and_returns_updated(self) -> None:
        original = _session_data("abc-123", "processing")
        self._table().select.return_value.eq.return_value.execute.return_value = _mock_response([original])
        self._table().update.return_value.eq.return_value.execute.return_value = _mock_response([])

        updated = store.update_session("abc-123", status="pending_review")

        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "pending_review")

    def test_update_session_sends_only_kwargs_to_supabase(self) -> None:
        original = _session_data("abc-123")
        self._table().select.return_value.eq.return_value.execute.return_value = _mock_response([original])
        self._table().update.return_value.eq.return_value.execute.return_value = _mock_response([])

        store.update_session("abc-123", status="pending_review", error="Falha na extração")

        update_payload = self._table().update.call_args[0][0]
        self.assertEqual(update_payload["status"], "pending_review")
        self.assertEqual(update_payload["error"], "Falha na extração")
        self.assertNotIn("session_id", update_payload)

    def test_update_session_returns_none_for_unknown_id(self) -> None:
        self._table().select.return_value.eq.return_value.execute.return_value = _mock_response([])

        result = store.update_session("nao-existe", status="failed")

        self.assertIsNone(result)
        self._table().update.assert_not_called()

    # ── delete_session ────────────────────────────────────────────────────────

    def test_delete_session_calls_supabase_delete(self) -> None:
        self._table().delete.return_value.eq.return_value.execute.return_value = _mock_response([])

        store.delete_session("abc-123")

        self._mock_client.table.assert_called_with("review_sessions")
        self._table().delete.assert_called_once()
        self._table().delete.return_value.eq.assert_called_with("session_id", "abc-123")

    # ── save_session ──────────────────────────────────────────────────────────

    def test_save_session_uses_upsert(self) -> None:
        now = datetime.now(tz=timezone.utc)
        session = ReviewSession(
            session_id="abc-123",
            status="pending_review",
            created_at=now.isoformat(),
            expires_at=(now + timedelta(hours=24)).isoformat(),
        )
        self._table().upsert.return_value.execute.return_value = _mock_response([])

        store.save_session(session)

        self._table().upsert.assert_called_once()
        upserted = self._table().upsert.call_args[0][0]
        self.assertEqual(upserted["session_id"], "abc-123")


if __name__ == "__main__":
    unittest.main()
