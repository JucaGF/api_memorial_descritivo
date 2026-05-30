from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException
from starlette.requests import Request

from app.config import get_settings
from app.services.user_profile_store import (
    ROLE_OWNER,
    STATUS_ACTIVE,
    UserProfile,
    get_profile,
)


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    email: str
    display_name: str
    role: str
    status: str

    @classmethod
    def from_profile(cls, profile: UserProfile) -> "CurrentUser":
        return cls(
            user_id=profile.user_id,
            email=profile.email,
            display_name=profile.display_name,
            role=profile.role,
            status=profile.status,
        )


class AuthError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _extract_bearer_token(request: Request) -> str:
    raw_header = request.headers.get("authorization", "").strip()
    parts = raw_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthError(
            401,
            "auth_missing_token",
            "Faça login para acessar a plataforma.",
        )
    return parts[1].strip()


def _auth_client() -> Any:
    from supabase import create_client

    settings = get_settings().generated_memorial_storage
    return create_client(settings.supabase_url, settings.supabase_key)


def _user_attr(user: Any, name: str) -> Any:
    if isinstance(user, dict):
        return user.get(name)
    return getattr(user, name, None)


def _validate_token(token: str) -> tuple[str, str]:
    try:
        response = _auth_client().auth.get_user(token)
    except Exception as error:
        raise AuthError(
            401,
            "auth_invalid_token",
            "Sessão inválida ou expirada. Faça login novamente.",
        ) from error

    user = getattr(response, "user", None) or response
    user_id = str(_user_attr(user, "id") or "")
    email = str(_user_attr(user, "email") or "")
    if not user_id:
        raise AuthError(
            401,
            "auth_invalid_token",
            "Sessão inválida ou expirada. Faça login novamente.",
        )
    return user_id, email


async def require_user(request: Request) -> CurrentUser:
    try:
        token = _extract_bearer_token(request)
        user_id, email = _validate_token(token)
        profile = get_profile(user_id)
        if profile is None:
            raise AuthError(
                403,
                "auth_profile_missing",
                "Usuário sem perfil ativo na plataforma.",
            )
        if profile.status != STATUS_ACTIVE:
            raise AuthError(
                403,
                "auth_user_inactive",
                "Usuário inativo na plataforma.",
            )
        if email and profile.email != email:
            profile = UserProfile(
                user_id=profile.user_id,
                email=email,
                display_name=profile.display_name,
                role=profile.role,
                status=profile.status,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
            )
        return CurrentUser.from_profile(profile)
    except AuthError as error:
        raise HTTPException(status_code=error.status_code, detail=error.message) from error


async def require_owner(current_user: CurrentUser = Depends(require_user)) -> CurrentUser:
    if current_user.role != ROLE_OWNER:
        raise HTTPException(
            status_code=403,
            detail="Apenas o usuário administrador pode acessar este recurso.",
        )
    return current_user
