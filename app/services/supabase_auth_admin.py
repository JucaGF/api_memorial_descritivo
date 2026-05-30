from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import get_settings

_client_instance: Any = None


class SupabaseAuthAdminError(RuntimeError):
    """Safe error for Supabase Auth admin failures."""


class SupabaseAuthUserAlreadyExistsError(SupabaseAuthAdminError):
    """Raised when Auth rejects a duplicate email."""


@dataclass(frozen=True)
class CreatedAuthUser:
    user_id: str
    email: str


def _storage_settings():
    return get_settings().generated_memorial_storage


def _client() -> Any:
    global _client_instance
    if _client_instance is None:
        from supabase import create_client

        settings = _storage_settings()
        _client_instance = create_client(settings.supabase_url, settings.supabase_key)
    return _client_instance


def _extract_user(value: Any) -> Any:
    return getattr(value, "user", None) or value


def create_auth_user(
    *,
    email: str,
    password: str,
    display_name: str,
    role: str,
) -> CreatedAuthUser:
    payload = {
        "email": email,
        "password": password,
        "email_confirm": True,
        "user_metadata": {"display_name": display_name},
        "app_metadata": {"role": role},
    }
    try:
        response = _client().auth.admin.create_user(payload)
    except Exception as error:
        message = str(error).lower()
        if "already" in message or "duplicate" in message or "registered" in message:
            raise SupabaseAuthUserAlreadyExistsError("Usuário já existe.") from error
        raise SupabaseAuthAdminError("Falha ao criar usuário no Supabase Auth.") from error

    user = _extract_user(response)
    user_id = str(getattr(user, "id", "") or "")
    created_email = str(getattr(user, "email", "") or email)
    if not user_id:
        raise SupabaseAuthAdminError("Supabase Auth não retornou o usuário criado.")
    return CreatedAuthUser(user_id=user_id, email=created_email)


def delete_auth_user(user_id: str) -> None:
    try:
        _client().auth.admin.delete_user(user_id)
    except Exception as error:
        raise SupabaseAuthAdminError("Falha ao excluir usuário no Supabase Auth.") from error
