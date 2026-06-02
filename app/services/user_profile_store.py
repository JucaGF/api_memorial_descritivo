from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings

USER_PROFILES_TABLE = "user_profiles"
ROLE_OWNER = "owner"
ROLE_USER = "user"
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"

_client_instance: Any = None


class UserProfileError(RuntimeError):
    """Safe error for user profile persistence failures."""


class UserProfileNotFoundError(UserProfileError):
    """Raised when a user profile does not exist."""


class DuplicateUserProfileError(UserProfileError):
    """Raised when a user profile/email already exists."""


class LastOwnerError(UserProfileError):
    """Raised when an operation would remove the last active owner."""


class SelfManagementError(UserProfileError):
    """Raised when an owner tries to deactivate or demote themselves."""


@dataclass(frozen=True)
class UserProfile:
    user_id: str
    email: str
    display_name: str
    role: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None


def _storage_settings():
    return get_settings().generated_memorial_storage


def _client() -> Any:
    global _client_instance
    if _client_instance is None:
        from supabase import create_client

        settings = _storage_settings()
        _client_instance = create_client(settings.supabase_url, settings.supabase_key)
    return _client_instance


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _from_record(record: dict[str, Any]) -> UserProfile:
    return UserProfile(
        user_id=str(record["user_id"]),
        email=str(record["email"]),
        display_name=str(record["display_name"]),
        role=str(record["role"]),
        status=str(record["status"]),
        created_at=record.get("created_at"),
        updated_at=record.get("updated_at"),
    )


def _normalize_display_name(value: str) -> str:
    display_name = value.strip()
    if len(display_name) < 2 or len(display_name) > 80:
        raise UserProfileError("Nome de usuário deve ter entre 2 e 80 caracteres.")
    return display_name


def get_profile(user_id: str) -> UserProfile | None:
    response = (
        _client()
        .table(USER_PROFILES_TABLE)
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        return None
    return _from_record(response.data[0])


def list_profiles() -> list[UserProfile]:
    response = (
        _client()
        .table(USER_PROFILES_TABLE)
        .select("*")
        .order("created_at", desc=False)
        .execute()
    )
    return [_from_record(record) for record in (response.data or [])]


def create_profile(
    *,
    user_id: str,
    email: str,
    display_name: str,
    role: str = ROLE_USER,
    status: str = STATUS_ACTIVE,
    created_by: str | None = None,
) -> UserProfile:
    record = {
        "user_id": user_id,
        "email": email.strip().lower(),
        "display_name": _normalize_display_name(display_name),
        "role": role,
        "status": status,
        "created_by": created_by,
    }
    try:
        response = _client().table(USER_PROFILES_TABLE).insert(record).execute()
    except Exception as error:
        if "duplicate" in str(error).lower() or "already" in str(error).lower():
            raise DuplicateUserProfileError("Usuário já existe.") from error
        raise UserProfileError("Falha ao criar perfil de usuário.") from error
    data = response.data[0] if response.data else record
    return _from_record(data)


def update_my_display_name(user_id: str, display_name: str) -> UserProfile:
    payload = {
        "display_name": _normalize_display_name(display_name),
        "updated_at": _now(),
    }
    response = (
        _client()
        .table(USER_PROFILES_TABLE)
        .update(payload)
        .eq("user_id", user_id)
        .execute()
    )
    if not response.data:
        profile = get_profile(user_id)
        if profile is None:
            raise UserProfileNotFoundError("Usuário não encontrado.")
        return profile
    return _from_record(response.data[0])


def _active_owner_count() -> int:
    response = (
        _client()
        .table(USER_PROFILES_TABLE)
        .select("user_id")
        .eq("role", ROLE_OWNER)
        .eq("status", STATUS_ACTIVE)
        .execute()
    )
    return len(response.data or [])


def update_profile_as_owner(
    *,
    target_user_id: str,
    actor_user_id: str,
    display_name: str | None = None,
    role: str | None = None,
    status: str | None = None,
) -> UserProfile:
    profile = get_profile(target_user_id)
    if profile is None:
        raise UserProfileNotFoundError("Usuário não encontrado.")

    removing_owner = profile.role == ROLE_OWNER and (
        role == ROLE_USER or status == STATUS_INACTIVE
    )
    if removing_owner and target_user_id == actor_user_id:
        raise SelfManagementError("O owner não pode remover o próprio acesso.")
    if removing_owner and _active_owner_count() <= 1:
        raise LastOwnerError("Não é possível remover o último owner ativo.")

    payload: dict[str, Any] = {"updated_at": _now()}
    if display_name is not None:
        payload["display_name"] = _normalize_display_name(display_name)
    if role is not None:
        payload["role"] = role
    if status is not None:
        payload["status"] = status

    response = (
        _client()
        .table(USER_PROFILES_TABLE)
        .update(payload)
        .eq("user_id", target_user_id)
        .execute()
    )
    if not response.data:
        updated = get_profile(target_user_id)
        if updated is None:
            raise UserProfileNotFoundError("Usuário não encontrado.")
        return updated
    return _from_record(response.data[0])


def deactivate_profile_as_owner(target_user_id: str, actor_user_id: str) -> UserProfile:
    return update_profile_as_owner(
        target_user_id=target_user_id,
        actor_user_id=actor_user_id,
        status=STATUS_INACTIVE,
    )


def validate_profile_removal_as_owner(target_user_id: str, actor_user_id: str) -> UserProfile:
    profile = get_profile(target_user_id)
    if profile is None:
        raise UserProfileNotFoundError("Usuário não encontrado.")
    if target_user_id == actor_user_id:
        raise SelfManagementError("O owner não pode remover o próprio acesso.")
    if (
        profile.role == ROLE_OWNER
        and profile.status == STATUS_ACTIVE
        and _active_owner_count() <= 1
    ):
        raise LastOwnerError("Não é possível remover o último owner ativo.")
    return profile
