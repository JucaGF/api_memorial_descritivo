# GLP Diameter Normalization Design

## Goal

Ensure `ramal.primario_diametro` in the GLP memorial context is always expressed in millimeters before validation and rendering, even when extraction sources express the diameter in inches.

## Scope

In scope:
- GLP file-based extraction path
- normalization of `ramal.primario_diametro`
- targeted prompt guidance for GLP extraction
- tests covering normalization and GLP pipeline behavior

Out of scope:
- broader GLP source-priority refactor
- appliance-count reconciliation
- template wording changes unrelated to diameter normalization

## Design

The GLP schema already expects `ramal.primario_diametro` as a numeric millimeter value. The safest implementation is to normalize the merged GLP extraction context before schema validation.

Normalization rules:
- numeric values are treated as millimeters and preserved
- strings ending in `mm` are parsed as millimeters
- inch notation like `1"`, `1 1/4"`, `3/4"` is converted to millimeters using `25.4 mm/in`
- normalized result is rounded to one decimal place to keep deterministic numeric output

This logic belongs in the GLP mapping/normalization layer rather than the renderer so the validated context matches the final memorial contract.

## Files Likely To Change

- `app/services/pipeline_from_files.py`
- `app/services/context_builder.py`
- `app/services/llm_extractor.py`
- `tests/test_pipeline_from_files.py`
- `tests/test_api.py`

## Verification

- targeted GLP pipeline tests
- targeted GLP API tests
- LLM extractor regression tests for prompt-facing behavior when needed
