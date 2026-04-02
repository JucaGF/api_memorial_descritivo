from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


class SessionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = TemporaryDirectory()
        self._sessions_path = Path(self._temp_dir.name)
        self._patcher = patch(
            "app.services.session_store._sessions_dir",
            return_value=self._sessions_path,
        )
        self._patcher.start()
        # Re-import after patching so the module uses the patched dir
        from app.services import session_store
        self._store = session_store

    def tearDown(self) -> None:
        self._patcher.stop()
        self._temp_dir.cleanup()

    def test_create_session_returns_uuid_string(self) -> None:
        session_id = self._store.create_session()

        self.assertIsInstance(session_id, str)
        self.assertEqual(len(session_id), 36)  # UUID format

    def test_create_session_writes_json_file(self) -> None:
        session_id = self._store.create_session()

        session_file = self._sessions_path / f"{session_id}.json"
        self.assertTrue(session_file.exists())

    def test_create_session_sets_processing_status(self) -> None:
        session_id = self._store.create_session()
        session = self._store.load_session(session_id)

        self.assertEqual(session.status, self._store.STATUS_PROCESSING)

    def test_create_session_sets_expires_at_24h_in_future(self) -> None:
        before = datetime.now(tz=timezone.utc)
        session_id = self._store.create_session()
        session = self._store.load_session(session_id)

        expires_at = datetime.fromisoformat(session.expires_at)
        created_at = datetime.fromisoformat(session.created_at)
        delta = expires_at - created_at

        self.assertAlmostEqual(delta.total_seconds(), 86400, delta=5)

    def test_load_session_returns_none_for_unknown_id(self) -> None:
        result = self._store.load_session("00000000-0000-0000-0000-000000000000")

        self.assertIsNone(result)

    def test_load_session_returns_session_with_correct_id(self) -> None:
        session_id = self._store.create_session()
        session = self._store.load_session(session_id)

        self.assertEqual(session.session_id, session_id)

    def test_load_session_returns_none_for_expired_session(self) -> None:
        session_id = "expired-session"
        expired_session = self._store.ReviewSession(
            session_id=session_id,
            status=self._store.STATUS_PENDING_REVIEW,
            created_at=(datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat(),
            expires_at=(datetime.now(tz=timezone.utc) - timedelta(minutes=1)).isoformat(),
        )
        self._store.save_session(expired_session)

        loaded = self._store.load_session(session_id)

        self.assertIsNone(loaded)

    def test_load_session_removes_expired_session_file(self) -> None:
        session_id = "expired-session"
        expired_session = self._store.ReviewSession(
            session_id=session_id,
            status=self._store.STATUS_PENDING_REVIEW,
            created_at=(datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat(),
            expires_at=(datetime.now(tz=timezone.utc) - timedelta(minutes=1)).isoformat(),
        )
        self._store.save_session(expired_session)

        self._store.load_session(session_id)

        self.assertFalse((self._sessions_path / f"{session_id}.json").exists())

    def test_update_session_changes_specified_fields(self) -> None:
        session_id = self._store.create_session()

        updated = self._store.update_session(
            session_id,
            status=self._store.STATUS_PENDING_REVIEW,
            partial_context={"obra": {"nome": "Makai"}},
        )

        self.assertEqual(updated.status, self._store.STATUS_PENDING_REVIEW)
        self.assertEqual(updated.partial_context["obra"]["nome"], "Makai")

    def test_update_session_preserves_unchanged_fields(self) -> None:
        session_id = self._store.create_session()
        original = self._store.load_session(session_id)

        self._store.update_session(session_id, status=self._store.STATUS_FAILED, error="Erro")
        updated = self._store.load_session(session_id)

        self.assertEqual(updated.created_at, original.created_at)
        self.assertEqual(updated.expires_at, original.expires_at)

    def test_update_session_persists_to_file(self) -> None:
        session_id = self._store.create_session()
        self._store.update_session(session_id, status=self._store.STATUS_PENDING_REVIEW)

        raw = json.loads((self._sessions_path / f"{session_id}.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["status"], self._store.STATUS_PENDING_REVIEW)

    def test_update_session_returns_none_for_unknown_id(self) -> None:
        result = self._store.update_session("nao-existe", status="failed")

        self.assertIsNone(result)

    def test_update_session_returns_none_for_expired_session(self) -> None:
        session_id = "expired-session"
        expired_session = self._store.ReviewSession(
            session_id=session_id,
            status=self._store.STATUS_PENDING_REVIEW,
            created_at=(datetime.now(tz=timezone.utc) - timedelta(days=2)).isoformat(),
            expires_at=(datetime.now(tz=timezone.utc) - timedelta(minutes=1)).isoformat(),
        )
        self._store.save_session(expired_session)

        updated = self._store.update_session(session_id, status=self._store.STATUS_FAILED)

        self.assertIsNone(updated)
        self.assertFalse((self._sessions_path / f"{session_id}.json").exists())

    def test_delete_session_removes_file(self) -> None:
        session_id = self._store.create_session()
        session_file = self._sessions_path / f"{session_id}.json"
        self.assertTrue(session_file.exists())

        self._store.delete_session(session_id)

        self.assertFalse(session_file.exists())

    def test_delete_session_on_unknown_id_does_not_raise(self) -> None:
        try:
            self._store.delete_session("nao-existe")
        except Exception as exc:
            self.fail(f"delete_session levantou exceção inesperada: {exc}")

    def test_session_corrections_default_to_empty_dict(self) -> None:
        session_id = self._store.create_session()
        session = self._store.load_session(session_id)

        self.assertEqual(session.corrections, {})

    def test_session_error_defaults_to_none(self) -> None:
        session_id = self._store.create_session()
        session = self._store.load_session(session_id)

        self.assertIsNone(session.error)


if __name__ == "__main__":
    unittest.main()
