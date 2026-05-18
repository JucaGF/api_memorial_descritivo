from __future__ import annotations

import importlib
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient


def _base_env() -> dict[str, str]:
    return {
        "APP_ENV": "test",
        "CORS_ALLOWED_ORIGINS": "",
        "SUPABASE_URL": "",
        "SUPABASE_KEY": "",
        "GENERATED_MEMORIALS_BUCKET": "generated-memorials",
    }


class AppConfigTests(unittest.TestCase):
    def test_load_settings_uses_local_defaults_for_test_environment(self) -> None:
        with patch.dict(os.environ, _base_env(), clear=False):
            from app.config import AppEnvironment, get_settings

            settings = get_settings()

        self.assertEqual(settings.app_env, AppEnvironment.TEST)
        self.assertIn("http://localhost:5173", settings.cors_allowed_origins)
        self.assertIn("http://127.0.0.1:5173", settings.cors_allowed_origins)

    def test_load_settings_parses_and_normalizes_production_origins(self) -> None:
        with patch.dict(
            os.environ,
            {
                **_base_env(),
                "APP_ENV": "production",
                "CORS_ALLOWED_ORIGINS": " https://dashboard.example.com, ,https://admin.example.com  ",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "service-role-key",
            },
            clear=False,
        ):
            from app.config import AppEnvironment, get_settings

            settings = get_settings()

        self.assertEqual(settings.app_env, AppEnvironment.PRODUCTION)
        self.assertEqual(
            settings.cors_allowed_origins,
            [
                "https://dashboard.example.com",
                "https://admin.example.com",
            ],
        )

    def test_create_app_rejects_production_without_explicit_cors_origins(self) -> None:
        with patch.dict(
            os.environ,
            {
                **_base_env(),
                "APP_ENV": "production",
                "CORS_ALLOWED_ORIGINS": " , ",
            },
            clear=False,
        ):
            import app.main
            from app.config import ConfigurationError

            with self.assertRaises(ConfigurationError):
                importlib.reload(app.main)

    def test_create_app_rejects_production_without_explicit_generated_memorial_bucket(self) -> None:
        env = _base_env()
        env.pop("GENERATED_MEMORIALS_BUCKET", None)
        with patch.dict(
            os.environ,
            {
                **env,
                "APP_ENV": "production",
                "CORS_ALLOWED_ORIGINS": "https://dashboard.example.com",
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "service-role-key",
            },
            clear=True,
        ):
            from app.config import ConfigurationError, get_settings

            with self.assertRaises(ConfigurationError):
                get_settings()

    def test_create_app_rejects_production_without_supabase_credentials_for_generated_memorials(self) -> None:
        with patch.dict(
            os.environ,
            {
                **_base_env(),
                "APP_ENV": "production",
                "CORS_ALLOWED_ORIGINS": "https://dashboard.example.com",
                "GENERATED_MEMORIALS_BUCKET": "generated-memorials",
                "SUPABASE_URL": "",
                "SUPABASE_KEY": "",
            },
            clear=True,
        ):
            from app.config import ConfigurationError, get_settings

            with self.assertRaises(ConfigurationError):
                get_settings()

    def test_cors_allows_explicit_origin(self) -> None:
        from app.config import AppEnvironment, AppSettings
        from app.main import create_app

        app = create_app(
            AppSettings(
                app_env=AppEnvironment.TEST,
                cors_allowed_origins=["http://localhost:5173"],
            )
        )
        client = TestClient(app)

        response = client.options(
            "/health/live",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            "http://localhost:5173",
        )

    def test_upload_limits_have_safe_defaults(self) -> None:
        with patch.dict(os.environ, _base_env(), clear=False):
            from app.config import get_settings

            settings = get_settings()

        self.assertEqual(settings.upload_limits.max_file_count, 10)
        self.assertEqual(settings.upload_limits.max_file_size_mb, 50)
        self.assertEqual(settings.upload_limits.max_total_upload_mb, 200)
        self.assertEqual(settings.upload_limits.max_pdf_pages, 100)

    def test_upload_limits_can_be_overridden_via_env(self) -> None:
        env = {
            **_base_env(),
            "MAX_FILE_COUNT": "25",
            "MAX_FILE_SIZE_MB": "100",
            "MAX_TOTAL_UPLOAD_MB": "500",
            "MAX_PDF_PAGES": "300",
        }
        with patch.dict(os.environ, env, clear=False):
            from app.config import get_settings

            settings = get_settings()

        self.assertEqual(settings.upload_limits.max_file_count, 25)
        self.assertEqual(settings.upload_limits.max_file_size_mb, 100)
        self.assertEqual(settings.upload_limits.max_total_upload_mb, 500)
        self.assertEqual(settings.upload_limits.max_pdf_pages, 300)

    def test_invalid_upload_limit_raises_configuration_error(self) -> None:
        with patch.dict(
            os.environ,
            {**_base_env(), "MAX_FILE_COUNT": "-1"},
            clear=False,
        ):
            from app.config import ConfigurationError, get_settings

            with self.assertRaises(ConfigurationError):
                get_settings()

    def test_cors_does_not_allow_unconfigured_origin(self) -> None:
        from app.config import AppEnvironment, AppSettings
        from app.main import create_app

        app = create_app(
            AppSettings(
                app_env=AppEnvironment.TEST,
                cors_allowed_origins=["http://localhost:5173"],
            )
        )
        client = TestClient(app)

        response = client.options(
            "/health/live",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIsNone(response.headers.get("access-control-allow-origin"))


if __name__ == "__main__":
    unittest.main()
