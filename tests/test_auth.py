from __future__ import annotations

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api.auth import CurrentUser, require_owner, require_user
from app.services.user_profile_store import UserProfile


def _request(auth_header: str | None = "Bearer valid-token") -> MagicMock:
    request = MagicMock()
    request.headers = {}
    if auth_header is not None:
        request.headers["authorization"] = auth_header
    request.state.request_id = "req-auth"
    return request


def _auth_response() -> MagicMock:
    user = MagicMock()
    user.id = "user-123"
    user.email = "usuario@example.com"
    response = MagicMock()
    response.user = user
    return response


def _profile(
    *,
    role: str = "user",
    status: str = "active",
) -> UserProfile:
    return UserProfile(
        user_id="user-123",
        email="usuario@example.com",
        display_name="Usuario Teste",
        role=role,
        status=status,
    )


class AuthDependencyTests(unittest.TestCase):
    def test_require_user_rejects_missing_authorization_header(self) -> None:
        with self.assertRaises(HTTPException) as captured:
            asyncio.run(require_user(_request(auth_header=None)))

        self.assertEqual(captured.exception.status_code, 401)
        self.assertIn("login", str(captured.exception.detail).lower())

    @patch("app.api.auth.get_profile", return_value=_profile(status="inactive"))
    @patch("app.api.auth._auth_client")
    def test_require_user_rejects_inactive_profile(self, auth_client_mock, _profile_mock) -> None:
        auth_client_mock.return_value.auth.get_user.return_value = _auth_response()

        with self.assertRaises(HTTPException) as captured:
            asyncio.run(require_user(_request()))

        self.assertEqual(captured.exception.status_code, 403)
        self.assertIn("inativo", str(captured.exception.detail).lower())

    @patch("app.api.auth.get_profile", return_value=_profile(role="user"))
    @patch("app.api.auth._auth_client")
    def test_require_user_returns_current_user_for_active_profile(self, auth_client_mock, _profile_mock) -> None:
        auth_client_mock.return_value.auth.get_user.return_value = _auth_response()

        current_user = asyncio.run(require_user(_request()))

        self.assertEqual(current_user.user_id, "user-123")
        self.assertEqual(current_user.email, "usuario@example.com")
        self.assertEqual(current_user.display_name, "Usuario Teste")
        self.assertEqual(current_user.role, "user")

    def test_require_owner_rejects_regular_user(self) -> None:
        current_user = CurrentUser(
            user_id="user-123",
            email="usuario@example.com",
            display_name="Usuario Teste",
            role="user",
            status="active",
        )

        with self.assertRaises(HTTPException) as captured:
            asyncio.run(require_owner(current_user))

        self.assertEqual(captured.exception.status_code, 403)

    def test_require_owner_accepts_owner(self) -> None:
        current_user = CurrentUser(
            user_id="owner-123",
            email="owner@example.com",
            display_name="Owner",
            role="owner",
            status="active",
        )

        result = asyncio.run(require_owner(current_user))

        self.assertEqual(result.user_id, "owner-123")


if __name__ == "__main__":
    unittest.main()
