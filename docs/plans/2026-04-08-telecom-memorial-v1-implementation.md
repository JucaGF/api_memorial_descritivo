# Telecom memorial v1 implementation

## Goal

Implement support for `memorial telecom v1` following the same technical pattern already used by `memorial elétrico v1`, starting from the new template and schema that already exist in `templates/telecom/v1/`.

The first delivery should enable deterministic generation from JSON payload, with schema validation, DOCX rendering, API exposure, and automated tests. File-based extraction and review sessions for telecom should be added only after the direct JSON flow is stable.

## Why this change is needed

The repository now contains `templates/telecom/v1/schema.json` and `templates/telecom/v1/template.docx`, but the backend remains hardcoded to the electrical memorial flow.

Current limitation:

- there is no telecom validator
- there is no telecom renderer
- there is no telecom pipeline
- there are no telecom API routes
- there are no telecom fixtures or tests

This work matters now because the template/schema pair already exists, and the next useful step is to wire the backend to them without broad refactoring or accidental regressions in the electrical flow.

## Scope

### In scope

- implement telecom JSON generation flow end-to-end
- add telecom context builder behavior based on the telecom schema and template needs
- add telecom schema loading and validation
- add telecom DOCX rendering
- add telecom pipeline orchestration
- add telecom API endpoint for direct JSON generation
- add telecom fixtures and targeted automated tests
- document telecom template behavior in `templates/telecom/v1/notes.md` if gaps are found

### Out of scope

- generic multi-memorial registry/factory abstraction
- telecom file-ingestion pipeline
- telecom extraction mapper
- telecom LLM extraction
- telecom review-session flow
- refactoring electrical services into a fully generic architecture
- changing electrical API behavior

## Current state

The current implementation is centered on `eletrico v1`.

Relevant current modules:

- `app/services/context_builder.py`
  Contains `merge_context` and `build_memorial_eletrico_v1_context`. The builder injects defaults and electrical-specific normalization such as `obra.porcentagem_entre_*`, `nao_inclusos.tem_itens`, `gerador.circuitos_atendidos`, and null-filling for `energia`.

- `app/services/memorial_validator.py`
  Loads only `templates/eletrico/v1/schema.json` and exposes only `load_eletrico_v1_schema` and `validate_memorial_eletrico_v1_context`.

- `app/services/memorial_renderer.py`
  Renders only `templates/eletrico/v1/template.docx` via `render_memorial_eletrico_v1`, then verifies that no Jinja/internal markers remain.

- `app/services/pipeline.py`
  Exposes only `generate_memorial_eletrico_v1`, which chains electrical context builder, validator, and renderer.

- `app/api/routes.py`
  Exposes only `/api/v1/memoriais/eletrico` and the related electrical upload/from-files/session routes.

- `tests/`
  Test coverage is strongly electrical-specific. Existing tests already define the expected pattern for builder, validator, renderer, pipeline, and API behavior.

Telecom repository state:

- `templates/telecom/v1/schema.json` exists and currently defines only `documento.data_atual` plus the base `obra` fields.
- `templates/telecom/v1/template.docx` exists.
- `templates/telecom/v1/notes.md` exists, but still says the render engine is "a definir para telecom v1", which does not match the actual repo pattern if telecom is to follow electrical implementation.

Important observation:

- the current codebase is not yet modeled as a generic memorial engine; it is a stable electrical implementation with reusable patterns. The safest path is to add telecom with parallel telecom-specific functions first, then evaluate shared abstractions later if a second implemented memorial reveals clear duplication.

## Constraints to preserve

- keep the DOCX template as the source of truth for the final telecom memorial
- keep schema validation mandatory before rendering
- keep final generation deterministic
- do not use LLMs to generate the final memorial
- preserve existing electrical behavior and routes
- prefer small, localized changes over broad refactors
- rendered DOCX must not contain unresolved Jinja placeholders
- do not assume telecom needs the same optional/default fields as electrical; derive builder behavior from the telecom schema and template

## Milestones

1. Inspect the telecom template contract and define the minimum telecom context behavior
2. Implement telecom context builder, validator, renderer, and pipeline
3. Expose telecom JSON API route
4. Add telecom fixtures and targeted tests
5. Run targeted regression tests for telecom and electrical core flows
6. Decide whether telecom is ready for file-based ingestion/extraction as a separate follow-up task

## Detailed implementation notes

### Milestone 1. Inspect telecom template contract

Review:

- `templates/telecom/v1/template.docx`
- `templates/telecom/v1/schema.json`
- `templates/telecom/v1/notes.md`

Determine:

- whether the template uses only `documento.*` and `obra.*`
- whether there are hidden/defaulted fields not yet reflected in `schema.json`
- whether there are conditional sections or formatting constraints missing from `notes.md`

Expected outcome:

- a precise list of telecom fields actually required for render
- confirmation of whether `documento.data_atual` should default like electrical

### Milestone 2. Implement telecom service layer

Add telecom-specific functions alongside the existing electrical ones, avoiding premature generalization.

Likely files to update:

- `app/services/context_builder.py`
- `app/services/memorial_validator.py`
- `app/services/memorial_renderer.py`
- `app/services/pipeline.py`

Intended approach:

- add `build_memorial_telecom_v1_context`
- default `documento.data_atual` if omitted, matching the electrical UX unless the telecom template requires different behavior
- avoid adding electrical-only normalization to telecom
- add `TELECOM_V1_SCHEMA_PATH`, `load_telecom_v1_schema`, and `validate_memorial_telecom_v1_context`
- add `TELECOM_V1_TEMPLATE_PATH` and `render_memorial_telecom_v1`
- add `generate_memorial_telecom_v1`

Design rule:

- share only low-risk helpers already present, such as `merge_context`, dependency checks, and post-render token inspection
- keep telecom-specific naming explicit instead of introducing a generic memorial type dispatch layer in this pass

### Milestone 3. Expose telecom JSON API route

Likely file to update:

- `app/api/routes.py`

Add route equivalent to the electrical direct JSON endpoint:

- `POST /api/v1/memoriais/telecom`

Expected behavior:

- accept telecom JSON payload
- build telecom context
- validate against telecom schema
- render telecom DOCX
- return DOCX file response
- return structured `400` validation errors consistent with the current API style

Decision point:

- either reuse the current `_validation_error_response` helper with a more generic detail message parameter
- or add a parallel telecom-specific helper if that is the smaller change

### Milestone 4. Add fixtures and tests

Add telecom-specific targeted tests mirroring the electrical test structure.

Likely files to update or add:

- `tests/test_context_builder.py`
- `tests/test_memorial_validator.py`
- `tests/test_memorial_renderer.py`
- `tests/test_pipeline.py`
- `tests/test_api.py`
- `tests/fixtures/telecom_*.json`

Minimum telecom test coverage:

- valid telecom context passes validation
- missing `documento.data_atual` is auto-filled by builder if that remains the intended behavior
- missing required `obra` field raises structured validation errors
- additional root/documento/obra properties are rejected
- DOCX render succeeds and contains no unresolved template tokens
- API returns DOCX for valid telecom payload
- API returns `400` with structured errors for invalid telecom payload

### Milestone 5. Regression verification

Run telecom targeted tests plus the electrical tests most exposed to shared-module changes.

At minimum, re-run:

- context builder tests
- validator tests
- renderer tests
- pipeline tests
- API tests

### Milestone 6. Follow-up evaluation for file-based telecom flow

Only after telecom JSON generation is stable, inspect whether telecom should follow the electrical file path:

- `file_ingestion`
- `project_extractor`
- mapper
- optional review session
- optional LLM-assisted extraction

This should be a separate scoped task because telecom schema currently appears much smaller than electrical, and its extraction strategy may not justify immediate reuse of the electrical mapper/LLM structure.

## Risks and watchpoints

- `templates/telecom/v1/notes.md` may be incomplete relative to `template.docx`
- the telecom template may reference placeholders not yet present in `schema.json`
- overgeneralizing too early could destabilize the mature electrical path
- a shared validation/render helper refactor may look attractive but expand scope unnecessarily
- current validation error helper text is electrical-specific and may leak the wrong message on telecom failures if not adjusted carefully
- if telecom rendering needs extra normalization beyond `data_atual`, that behavior must be derived from the template rather than copied from electrical assumptions

## Test plan

Targeted tests after implementation:

```bash
python -m unittest tests.test_context_builder
python -m unittest tests.test_memorial_validator
python -m unittest tests.test_memorial_renderer
python -m unittest tests.test_pipeline
python -m unittest tests.test_api
```

If shared modules change more than expected, run the broader suite:

```bash
python -m unittest discover -s tests
```

Manual verification:

- render one telecom payload into DOCX
- inspect the rendered DOCX text for unresolved Jinja placeholders
- confirm returned filename/media type in the API response

## Definition of done

This plan is complete only when:

- telecom JSON generation is implemented end-to-end
- telecom schema validation is enforced before rendering
- telecom DOCX renders from the committed template
- the new telecom API route works
- targeted telecom and affected electrical tests pass
- electrical behavior remains unchanged
- `templates/telecom/v1/notes.md` is coherent with the implemented telecom flow

## Progress log

- 2026-04-08 00:00: inspected repository guidance in `README.md`, `AGENTS.md`, and `docs/PLANS.md`
- 2026-04-08 00:00: inspected current electrical implementation in validator, renderer, pipeline, routes, and tests
- 2026-04-08 00:00: inspected `templates/telecom/v1/schema.json`, `template.docx`, and `notes.md`; observed telecom schema currently covers only `documento` and `obra`
- 2026-04-08 00:00: wrote implementation plan prioritizing telecom JSON generation first, with file-based extraction explicitly deferred to a follow-up task
