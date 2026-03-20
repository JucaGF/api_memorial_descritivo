from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services.context_builder import build_memorial_eletrico_v1_context
from app.services.memorial_renderer import render_memorial_eletrico_v1
from app.services.memorial_validator import validate_memorial_eletrico_v1_context


@dataclass(frozen=True)
class PipelineResult:
    context: dict[str, Any]
    output_path: Path


def generate_memorial_eletrico_v1(
    raw_payload: dict[str, Any],
    output_path: Path,
) -> PipelineResult:
    context = build_memorial_eletrico_v1_context(raw_payload)
    validate_memorial_eletrico_v1_context(context)
    rendered_output_path = render_memorial_eletrico_v1(context, output_path)
    return PipelineResult(context=context, output_path=rendered_output_path)
