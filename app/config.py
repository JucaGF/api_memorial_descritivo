from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is invalid."""


class AppEnvironment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"


_LOCAL_DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


@dataclass(frozen=True)
class GeneratedMemorialStorageSettings:
    bucket: str
    signed_url_ttl_seconds: int
    supabase_url: str
    supabase_key: str


@dataclass(frozen=True)
class AppSettings:
    app_env: AppEnvironment
    cors_allowed_origins: list[str]
    generated_memorial_storage: GeneratedMemorialStorageSettings = field(
        default_factory=lambda: GeneratedMemorialStorageSettings(
            bucket="generated-memorials",
            signed_url_ttl_seconds=3600,
            supabase_url="",
            supabase_key="",
        )
    )

    @property
    def readiness_configuration_status(self) -> str:
        return "strict" if self.app_env is AppEnvironment.PRODUCTION else "default"


def _parse_app_env(raw_value: str | None) -> AppEnvironment:
    normalized = (raw_value or AppEnvironment.LOCAL.value).strip().lower()
    try:
        return AppEnvironment(normalized)
    except ValueError as exc:
        raise ConfigurationError("APP_ENV inválido. Use local, test ou production.") from exc


def _parse_cors_origins(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


def _parse_positive_int(raw_value: str | None, env_name: str, default: int) -> int:
    value = (raw_value or str(default)).strip()
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{env_name} deve ser um inteiro positivo.") from exc
    if parsed <= 0:
        raise ConfigurationError(f"{env_name} deve ser um inteiro positivo.")
    return parsed


def get_settings() -> AppSettings:
    app_env = _parse_app_env(os.getenv("APP_ENV"))
    raw_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS")
    if raw_cors_origins is None:
        raw_cors_origins = os.getenv("CORS_ORIGINS")

    cors_allowed_origins = _parse_cors_origins(raw_cors_origins)
    if app_env in {AppEnvironment.LOCAL, AppEnvironment.TEST} and not cors_allowed_origins:
        cors_allowed_origins = list(_LOCAL_DEFAULT_CORS_ORIGINS)

    if app_env is AppEnvironment.PRODUCTION and not cors_allowed_origins:
        raise ConfigurationError(
            "CORS_ALLOWED_ORIGINS deve ser configurado em production."
        )

    generated_memorials_bucket = os.getenv("GENERATED_MEMORIALS_BUCKET", "").strip()
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    supabase_key = os.getenv("SUPABASE_KEY", "").strip()
    signed_url_ttl_seconds = _parse_positive_int(
        os.getenv("GENERATED_MEMORIALS_SIGNED_URL_TTL"),
        "GENERATED_MEMORIALS_SIGNED_URL_TTL",
        3600,
    )

    if app_env is AppEnvironment.PRODUCTION:
        if "GENERATED_MEMORIALS_BUCKET" not in os.environ or not generated_memorials_bucket:
            raise ConfigurationError(
                "GENERATED_MEMORIALS_BUCKET deve ser configurado explicitamente em production."
            )
        if not supabase_url or not supabase_key:
            raise ConfigurationError(
                "SUPABASE_URL e SUPABASE_KEY devem ser configurados para os memoriais persistidos em production."
            )

    if not generated_memorials_bucket:
        generated_memorials_bucket = "generated-memorials"

    return AppSettings(
        app_env=app_env,
        cors_allowed_origins=cors_allowed_origins,
        generated_memorial_storage=GeneratedMemorialStorageSettings(
            bucket=generated_memorials_bucket,
            signed_url_ttl_seconds=signed_url_ttl_seconds,
            supabase_url=supabase_url,
            supabase_key=supabase_key,
        ),
    )
