# GLP Diameter Normalization

## Goal

Normalize the GLP `ramal.primario_diametro` field to millimeters in the file-based generation flow so the rendered memorial always shows millimeters even when extraction sources use inches.

## Why this change is needed

The current GLP generation can extract ramal diameter values from drawings in inch notation. The GLP schema and memorial output require millimeters. Without a dedicated normalization step, the generated memorial can render an incorrect value such as `1.25 mm` instead of the proper millimeter conversion.

## Scope

### In scope

- GLP-specific diameter normalization before validation/render
- inch-to-millimeter conversion for extracted GLP ramal diameter values
- targeted GLP tests covering normalization and end-to-end generation behavior
- minor GLP prompt tightening if needed

### Out of scope

- full GLP extraction conflict engine
- broader template wording cleanup
- non-GLP memorial changes

## Current state

- `app/services/pipeline_from_files.py` requires LLM extraction for GLP and merges LLM context with mapper gap fills.
- `app/services/context_builder.py` performs no GLP-specific normalization today.
- `app/services/llm_extractor.py` extracts GLP ramal fields but does not guarantee millimeter normalization.
- Existing GLP tests cover API success and LLM-path behavior, but not explicit inch-to-millimeter normalization.

## Constraints to preserve

- keep final generation deterministic
- preserve existing GLP API routes and payload shapes
- keep schema validation active
- keep GLP file generation dependent on required LLM extraction
- avoid unrelated refactors

## Milestones

1. Add failing tests for GLP diameter normalization
2. Implement GLP normalization in the file-generation path
3. Tighten prompt guidance only if needed
4. Run targeted GLP regressions

## Detailed implementation notes

1. Add tests that prove:
   - `1 1/4"` becomes `31.8` or the agreed deterministic millimeter value
   - plain numeric millimeter values stay unchanged
   - GLP from-files generation feeds normalized diameter into final generation
2. Add a GLP-only normalization helper after LLM/mapper merge and before validation.
3. Keep the helper narrow: only normalize `ramal.primario_diametro`.
4. If prompt guidance is adjusted, keep it additive and GLP-specific.

## Risks and watchpoints

- over-normalizing ambiguous numeric values that are already in millimeters
- introducing float formatting instability
- changing behavior outside the GLP file pipeline

## Test plan

```bash
uv run python -m unittest tests.test_pipeline_from_files
uv run python -m unittest tests.test_api
uv run python -m unittest tests.test_llm_extractor
```

## Definition of done

- GLP extracted ramal diameter is normalized to millimeters before validation/render
- targeted GLP tests pass
- existing GLP API behavior remains intact apart from corrected diameter output
