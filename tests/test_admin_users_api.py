from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import app.api.routes as routes
from app.api.auth import CurrentUser
from app.services.supabase_auth_admin import SupabaseAuthAdminError
from app.services.user_profile_store import LastOwnerError, SelfManagementError, UserProfile


def _request() -> MagicMock:
    request = MagicMock()
    request.state.request_id = "req-admin"
    return request


def _owner() -> CurrentUser:
    return CurrentUser(
        user_id="owner-123",
        email="owner@example.com",
        display_name="Owner",
        role="owner",
        status="active",
    )


def _profile(user_id: str = "user-123", role: str = "user") -> UserProfile:
    return UserProfile(
        user_id=user_id,
        email=f"{user_id}@example.com",
        display_name="Usuario Teste",
        role=role,
        status="active",
    )


class AdminUsersApiTests(unittest.TestCase):
    @patch("app.api.routes.list_profiles")
    def test_owner_lists_users(self, list_mock) -> None:
        list_mock.return_value = [_profile()]

        response = routes.list_admin_users(current_user=_owner())

        self.assertEqual(len(response.users), 1)
        self.assertEqual(response.users[0].user_id, "user-123")

    @patch("app.api.routes.create_profile")
    @patch("app.api.routes.create_auth_user")
    def test_owner_creates_user_profile_after_auth_user(self, auth_mock, profile_mock) -> None:
        auth_mock.return_value = MagicMock(user_id="new-123", email="novo@example.com")
        profile_mock.return_value = _profile("new-123")

        payload = routes.CreateAdminUserPayload(
            email="novo@example.com",
            password="senha-forte",
            display_name="Novo Usuario",
            role="user",
        )

        response = routes.create_admin_user(payload, _request(), current_user=_owner())

        self.assertEqual(response.user_id, "new-123")
        auth_mock.assert_called_once()
        profile_mock.assert_called_once()
        self.assertEqual(profile_mock.call_args.kwargs["created_by"], "owner-123")

    @patch("app.api.routes.update_profile_as_owner")
    def test_owner_cannot_remove_last_owner(self, update_mock) -> None:
        update_mock.side_effect = LastOwnerError("Não é possível remover o último owner ativo.")
        payload = routes.UpdateAdminUserPayload(role="user")

        response = routes.update_admin_user("owner-123", payload, _request(), current_user=_owner())

        self.assertEqual(response.status_code, 409)
        body = json.loads(response.body.decode("utf-8"))
        self.assertEqual(body["error"]["code"], "admin_user_update_not_allowed")

    @patch("app.api.routes.validate_profile_removal_as_owner")
    def test_owner_cannot_remove_self(self, validate_mock) -> None:
        validate_mock.side_effect = SelfManagementError("O owner não pode remover o próprio acesso.")

        response = routes.delete_admin_user("owner-123", _request(), current_user=_owner())

        self.assertEqual(response.status_code, 409)
        body = json.loads(response.body.decode("utf-8"))
        self.assertEqual(body["error"]["code"], "admin_user_delete_not_allowed")

    @patch("app.api.routes.delete_auth_user")
    @patch("app.api.routes.validate_profile_removal_as_owner")
    def test_owner_removes_user_from_auth_after_profile_validation(
        self, validate_mock, delete_auth_mock
    ) -> None:
        validate_mock.return_value = _profile("user-123")

        response = routes.delete_admin_user("user-123", _request(), current_user=_owner())

        self.assertEqual(response.user_id, "user-123")
        validate_mock.assert_called_once_with("user-123", "owner-123")
        delete_auth_mock.assert_called_once_with("user-123")

    @patch("app.api.routes.delete_auth_user")
    @patch("app.api.routes.validate_profile_removal_as_owner")
    def test_owner_gets_safe_error_when_auth_delete_fails(
        self, validate_mock, delete_auth_mock
    ) -> None:
        validate_mock.return_value = _profile("user-123")
        delete_auth_mock.side_effect = SupabaseAuthAdminError(
            "Falha ao excluir usuário no Supabase Auth."
        )

        response = routes.delete_admin_user("user-123", _request(), current_user=_owner())

        self.assertEqual(response.status_code, 503)
        body = json.loads(response.body.decode("utf-8"))
        self.assertEqual(body["error"]["code"], "admin_user_delete_failed")


if __name__ == "__main__":
    unittest.main()
