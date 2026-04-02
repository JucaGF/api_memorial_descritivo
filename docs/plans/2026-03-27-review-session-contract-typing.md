# Review-session contract typing

## Goal

Improve the typing of review-session API contracts without changing the current
external behavior of the endpoints.

The main target is `extraction_report`, which is already a meaningful part of
the review-session UX and appears in both session state and validation errors.
`partial_context` and `corrections` should be handled conservatively, keeping
their current flexibility unless the code clearly supports deeper typing.

## Why this change is needed

- `app/schemas/review_session.py` currently exposes `extraction_report`,
  `partial_context`, and `corrections` as generic `dict[str, Any]`.
- `extraction_report` is already structurally stable in the codebase, but the
  API contract does not communicate that stability.
- The current generic typing makes the API harder to document, validate, and
  evolve safely.
- This matters now because the review-session flow is already functional and is
  becoming a first-class workflow, so contract clarity has more value than it
  had in earlier exploratory stages.

## Scope

### In scope

- Inspect the current shape of `review_session` contracts in code and tests.
- Introduce explicit Pydantic models for `extraction_report` if the structure is
  stable enough.
- Reuse the existing extraction concepts (`FieldExtraction`,
  `ExtractionReport`) to avoid inventing a parallel contract.
- Keep the review-session endpoints and payload field names unchanged.
- Keep filesystem and Supabase persistence behavior aligned.

### Out of scope

- Deep typing of the full memorial context schema.
- Replacing `partial_context` or `corrections` with rigid schema-specific
  models.
- Refactoring session storage format beyond what typed serialization requires.
- Changing endpoint paths, field names, or high-level flow behavior.
- Touching template/schema rendering logic.

## Current state

- `SessionStateResponse` in `app/schemas/review_session.py` exposes:
  - `partial_context: dict[str, Any]`
  - `extraction_report: dict[str, Any]`
  - `corrections: dict[str, Any]`
- `ContextCorrectionsPayload` also uses `dict[str, Any]` for `corrections`.
- The review-session flow in `app/api/routes.py` stores and returns
  `partial_context` and `extraction_report` through session persistence:
  - `POST /api/v1/memoriais/eletrico/sessoes`
  - `GET /api/v1/memoriais/eletrico/sessoes/{session_id}`
  - `PATCH /api/v1/memoriais/eletrico/sessoes/{session_id}/contexto`
  - `POST /api/v1/memoriais/eletrico/sessoes/{session_id}/gerar`
- `app/services/extraction_mapper.py` already defines stable dataclasses:
  - `FieldExtraction`
  - `ExtractionReport`
  - `MappingResult`
- `FieldExtraction` currently has a stable shape:
  - `value`
  - `rule`
  - `evidence`
  - `confidence`
- `ExtractionReport` currently has a stable shape:
  - `filled: list[str]`
  - `missing: list[str]`
  - `pending: list[str]`
  - `evidence: dict[str, FieldExtraction]`
- Session persistence stores `extraction_report` as plain JSON/dict in:
  - `app/services/session_store.py`
  - `app/services/supabase_session_store.py`
- Existing tests already depend on the shape of `extraction_report`, especially
  `filled`, `missing`, `pending`, and `evidence`, but they do so through raw
  dict access rather than typed schema validation.

## Constraints to preserve

- Preserve current endpoint paths and payload field names.
- Preserve the current review-session flow behavior.
- Keep filesystem and Supabase persistence behavior aligned.
- Do not remove flexibility from `partial_context` and `corrections`
  prematurely.
- Do not introduce a broad refactor of mapper, session store, or routes.
- Keep the JSON shape of `extraction_report` compatible with what the current
  routes and tests already use.

## Milestones

1. Inspect current review-session contract usage and confirm stable structures.
2. Introduce typed API models for `FieldExtraction` and `ExtractionReport`.
3. Adapt review-session schemas to use typed `extraction_report` while keeping
   `partial_context` and `corrections` flexible.
4. Adjust serialization boundaries in routes/tests only if required.
5. Run targeted tests and the full suite.

## Detailed implementation notes

### Milestone 1

- Files:
  - `app/schemas/review_session.py`
  - `app/api/routes.py`
  - `app/services/extraction_mapper.py`
  - `app/services/session_store.py`
  - `app/services/supabase_session_store.py`
  - `tests/test_api.py`
  - `tests/test_extraction_mapper.py`
- Intended change:
  - Confirm that `extraction_report` is structurally stable enough for an
    explicit response model.
  - Confirm that `partial_context` and `corrections` are still too open-ended
    for rigid typing right now.

### Milestone 2

- Files:
  - `app/schemas/review_session.py`
- Intended change:
  - Add Pydantic models mirroring the stable extraction structures:
    - `FieldExtractionResponse`
    - `ExtractionReportResponse`
  - Keep field names identical to the current JSON contract.
  - Model `value` conservatively, likely as `Any`, because extracted fields are
    intentionally heterogeneous today.

### Milestone 3

- Files:
  - `app/schemas/review_session.py`
  - `app/api/routes.py`
- Intended change:
  - Change `SessionStateResponse.extraction_report` from `dict[str, Any]` to
    the typed report model.
  - Evaluate whether validation-error responses should remain manual JSON or
    optionally reuse the same typed extraction-report model without changing the
    external payload shape.
  - Keep `partial_context` and `corrections` as `dict[str, Any]`.

### Milestone 4

- Files:
  - `app/services/session_store.py`
  - `app/services/supabase_session_store.py`
  - `app/api/routes.py`
- Intended change:
  - Only if needed, ensure that persisted session data still round-trips
    cleanly into the typed schema.
  - Avoid changing the persisted `ReviewSession` dataclass shape unless schema
    validation reveals a real mismatch.

### Milestone 5

- Files:
  - `tests/test_api.py`
  - `tests/test_session_store.py`
  - `tests/test_supabase_session_store.py`
  - `tests/test_extraction_mapper.py`
- Intended change:
  - Add or adjust tests to assert that the API now validates/serializes a typed
    `extraction_report`.
  - Preserve current tests for flexible `partial_context` and `corrections`.

## Risks and watchpoints

- Over-typing `partial_context` too early would couple the review-session flow
  to a still-incomplete extraction surface.
- Over-typing `corrections` too early would make manual review patches harder to
  evolve and could break the current deep-merge behavior in
  `context_builder.merge_context`.
- Recreating Pydantic models that diverge from `FieldExtraction` /
  `ExtractionReport` would create two sources of truth for the same contract.
- Tightening the schema too much around `value` may break existing extracted
  fields with mixed scalar types.
- Session persistence stores plain dicts today; changes must not require a
  migration unless strictly necessary.

## Test plan

### Targeted tests

```bash
.venv/bin/python -m unittest tests.test_api
.venv/bin/python -m unittest tests.test_extraction_mapper
.venv/bin/python -m unittest tests.test_session_store
.venv/bin/python -m unittest tests.test_supabase_session_store
```

### Regression tests

```bash
.venv/bin/python -m unittest discover -s tests
```

### Manual verification

- Verify that `GET /api/v1/memoriais/eletrico/sessoes/{id}` still returns the
  same JSON keys for `extraction_report`.
- Verify that `PATCH /contexto` and `POST /gerar` do not need payload changes.

## Definition of done

- `extraction_report` has an explicit typed API model.
- The external JSON shape of the review-session endpoints remains compatible.
- `partial_context` and `corrections` remain flexible unless a very small,
  evidence-based wrapper is justified.
- Filesystem and Supabase session persistence remain compatible with the typed
  response schema.
- Relevant tests pass and the full suite remains green.

## Progress log

- 2026-03-27 00:00: inspected current review-session schemas, routes, mapper,
  session stores, and tests before implementation.
- 2026-03-27 00:00: confirmed that `extraction_report` is structurally stable,
  while `partial_context` and `corrections` are still intentionally open-ended.
- 2026-03-27 00:01: introduced explicit review-session schema models for
  `FieldExtraction` and `ExtractionReport` in `app/schemas/review_session.py`.
- 2026-03-27 00:02: kept `partial_context` and `corrections` flexible and used a
  conservative union for `SessionStateResponse.extraction_report` to preserve
  compatibility with existing persisted `{}` payloads.
- 2026-03-27 00:03: updated API tests to validate typed extraction-report shape
  and compatibility for empty extraction reports.

## Final outcome

- Changed:
  - Added explicit Pydantic models for `FieldExtraction` and
    `ExtractionReport` in the review-session schema layer.
  - Updated `SessionStateResponse` to expose a typed `extraction_report`
    contract while preserving compatibility with existing empty dict payloads.
  - Added API tests covering extraction-report shape and compatibility.

- Not changed:
  - Endpoint paths and field names
  - `partial_context` typing
  - `corrections` typing
  - session-store persistence format
  - extraction mapper behavior

- Tests run:
  - `.venv/bin/python -m unittest tests.test_api`
  - `.venv/bin/python -m unittest tests.test_extraction_mapper`
  - `.venv/bin/python -m unittest tests.test_session_store`
  - `.venv/bin/python -m unittest tests.test_supabase_session_store`
  - `.venv/bin/python -m unittest discover -s tests`

- Follow-ups:
  - Reassess lightweight wrappers for `partial_context` or `corrections` only
    after extraction coverage and review-session UX stabilize further.
