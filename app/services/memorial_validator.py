from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
ELETRICO_V1_SCHEMA_PATH = ROOT_DIR / "templates" / "eletrico" / "v1" / "schema.json"


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str
    validator: str


class MemorialValidationError(Exception):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        summary = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
        super().__init__(f"Contexto do memorial invalido. {summary}")


def has_jsonschema_dependency() -> bool:
    return importlib.util.find_spec("jsonschema") is not None


def _require_jsonschema_dependency() -> None:
    if has_jsonschema_dependency():
        return
    raise RuntimeError("Dependencia de validacao ausente: instale jsonschema.")


def load_eletrico_v1_schema() -> dict[str, Any]:
    with ELETRICO_V1_SCHEMA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _format_error_path(error: Any) -> str:
    if not error.absolute_path:
        return "$"
    return "$." + ".".join(str(part) for part in error.absolute_path)


def validate_memorial_eletrico_v1_context(
    context: dict[str, Any],
) -> list[ValidationIssue]:
    _require_jsonschema_dependency()
    from jsonschema import Draft202012Validator

    schema = load_eletrico_v1_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(context), key=lambda error: list(error.absolute_path))
    issues = [
        ValidationIssue(
            path=_format_error_path(error),
            message=error.message,
            validator=error.validator,
        )
        for error in errors
    ]
    if issues:
        raise MemorialValidationError(issues)
    return issues
