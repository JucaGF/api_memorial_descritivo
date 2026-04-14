# Gas Natural Memorial V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `memorial gas natural v1` as a separate memorial track with safe JSON generation first, then file-based extraction/generation support aligned with the current backend architecture.

**Architecture:** Follow the existing explicit per-memorial pattern already used for `eletrico v1` and `telecom v1`. Keep gas natural separate from future GLP, preserve deterministic final generation, and stage the file-based flow so mapper-only support lands first, while gas-specific LLM extraction is introduced early in the roadmap because good real-world extraction will likely depend on it.

**Tech Stack:** FastAPI, jsonschema, docxtpl, python-docx, unittest, optional OpenAI Responses API integration for extraction assistance.

---

## Why this change is needed

The repository already contains a committed gas natural template contract in `templates/gas_natural/v1/`, but there is no backend support for that memorial type yet.

Current gaps:

- no gas natural context builder
- no gas natural schema loader or validator
- no gas natural renderer
- no gas natural pipeline entrypoint
- no gas natural API routes
- no gas natural mapper/coverage flow
- no gas natural LLM extraction contract
- no gas natural fixtures or tests

This work matters now because product scope has already split gas into two distinct memorials: `gas natural` and `GLP`. Gas natural should become the first implemented gas track without creating a generic gas abstraction that blurs those contracts.

## Scope

### In scope

- implement a dedicated `gas_natural v1` memorial track
- support direct JSON generation end-to-end
- support upload and from-files API entrypoints
- support file-based extraction feedback with `extraction_report`
- add deterministic gas natural mapping and coverage logic
- add gas natural-specific LLM extraction support early in the roadmap
- add gas natural fixtures and targeted automated tests
- validate the gas natural DOCX template against the actual render path before broader backend work proceeds

### Out of scope

- implementation of `gas GLP`
- generic gas memorial abstraction or subtype registry
- gas natural review-session flow in the first pass
- broad refactors of shared memorial architecture
- changing electrical or telecom behavior except for low-risk shared helper reuse

## Current state

Current implemented memorial tracks:

- `eletrico v1`
  - JSON generation
  - file-based generation
  - review-session flow
  - optional LLM-assisted extraction

- `telecom v1`
  - JSON generation
  - file-based generation
  - optional LLM-assisted extraction
  - no review-session flow

Relevant repository behavior:

- [app/services/context_builder.py](/home/juca/Projects/api_memorial_descritivo/app/services/context_builder.py)
  - contains explicit builders per memorial
  - currently only shares low-risk helpers such as `merge_context` and `documento.data_atual` defaulting

- [app/services/memorial_validator.py](/home/juca/Projects/api_memorial_descritivo/app/services/memorial_validator.py)
  - loads schemas from template directories
  - exposes explicit validator functions per memorial

- [app/services/memorial_renderer.py](/home/juca/Projects/api_memorial_descritivo/app/services/memorial_renderer.py)
  - renders DOCX from template path
  - rejects rendered output that still contains unresolved Jinja or internal template markers

- [app/services/pipeline.py](/home/juca/Projects/api_memorial_descritivo/app/services/pipeline.py)
  - exposes explicit per-memorial generation entrypoints
  - does not use a registry/factory

- [app/services/pipeline_from_files.py](/home/juca/Projects/api_memorial_descritivo/app/services/pipeline_from_files.py)
  - exposes explicit per-memorial file flows
  - from-files behavior is "extract, validate, render if sufficient, otherwise raise validation error with extraction_report"
  - mapper-only remains valid even when LLM extraction is disabled

- [app/services/extraction_mapper.py](/home/juca/Projects/api_memorial_descritivo/app/services/extraction_mapper.py)
  - has electrical mapping and coverage logic
  - has telecom mapping and coverage logic
  - uses explicit extractable/pending field lists

- [app/services/llm_extractor.py](/home/juca/Projects/api_memorial_descritivo/app/services/llm_extractor.py)
  - keeps electrical and telecom LLM extraction contracts separate
  - uses `USE_LLM_EXTRACTION` as the feature switch

- [app/api/routes.py](/home/juca/Projects/api_memorial_descritivo/app/api/routes.py)
  - exposes explicit JSON, upload, and from-files routes for electrical and telecom
  - review-session routes exist only for electrical

Gas natural contract state:

- [templates/gas_natural/v1/schema.json](/home/juca/Projects/api_memorial_descritivo/templates/gas_natural/v1/schema.json) exists and requires:
  - `documento`
  - `obra`
  - `crm`
  - `dimensionamento`
  - `soma`
  - `ramal`
  - `valvula`
  - `numero`
  - `teto_ou_piso`
- [templates/gas_natural/v1/template.docx](/home/juca/Projects/api_memorial_descritivo/templates/gas_natural/v1/template.docx) exists
- [templates/gas_natural/v1/notes.md](/home/juca/Projects/api_memorial_descritivo/templates/gas_natural/v1/notes.md) exists

Known watchpoints from current inspection:

- the template placeholder for `valvula.esfera_diametro` may be fragmented across DOCX runs and must be proven in a real render
- the template includes wording that mentions `gás natural / GLP`, which may be intended boilerplate or a template defect
- the template appears to repeat `obra.nome` in the cover area and should be checked in render output, not assumed correct

## Constraints to preserve

- keep the DOCX template as the source of truth for final structure
- keep `schema.json` as the rendering contract
- keep final generation deterministic
- do not use LLM output as final memorial content generation
- validate context before rendering
- preserve electrical and telecom behavior
- keep gas natural explicitly separate from future GLP
- rendered DOCX must not contain unresolved Jinja placeholders
- keep filesystem/upload behavior consistent with existing routes and pipelines

## Ordered implementation approach

The work should be done in this order:

1. prove the gas natural template is render-safe
2. land JSON generation support
3. land upload/from-files route and pipeline scaffolding
4. land deterministic gas mapper and extraction coverage
5. land gas-specific LLM extraction support early, because real extraction quality is expected to require it
6. validate with real project files and refine extraction rules

Important interpretation:

- gas-specific LLM extraction should be planned early and implemented before claiming good real extraction quality
- but mapper-only and validation/error-report behavior should land first so the track works safely even when LLM extraction is disabled
- first-pass file support is successful if it returns either:
  - a rendered DOCX when extraction is sufficient
  - a structured validation error with `extraction_report` when extraction is incomplete

## File map

Expected new or modified files:

- Modify: `app/services/context_builder.py`
- Modify: `app/services/memorial_validator.py`
- Modify: `app/services/memorial_renderer.py`
- Modify: `app/services/pipeline.py`
- Modify: `app/services/extraction_mapper.py`
- Modify: `app/services/llm_extractor.py`
- Modify: `app/services/pipeline_from_files.py`
- Modify: `app/api/routes.py`
- Modify: `tests/test_context_builder.py`
- Modify: `tests/test_memorial_validator.py`
- Modify: `tests/test_memorial_renderer.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_extraction_mapper.py`
- Modify: `tests/test_llm_extractor.py`
- Modify: `tests/test_pipeline_from_files.py`
- Modify: `tests/test_api.py`
- Create: `tests/fixtures/gas_natural_base.json`
- Create: optional extra gas fixtures only if needed by targeted tests

### Task 1: Contract Gate And Render Verification

**Files:**
- Modify: `tests/test_memorial_renderer.py`
- Create: `tests/fixtures/gas_natural_base.json`

- [ ] **Step 1: Write the failing render and validation tests**

Add tests that:

- load a valid gas natural fixture
- validate it against the gas natural schema
- render the DOCX
- assert no Jinja tokens remain
- assert `valvula.esfera_diametro` appears correctly in rendered text

Expected new test names:

```python
def test_render_memorial_gas_natural_v1_generates_docx_without_template_tokens() -> None:
    ...

def test_render_memorial_gas_natural_v1_renders_valvula_esfera_diametro() -> None:
    ...
```

- [ ] **Step 2: Run the targeted renderer test to verify it fails**

Run:

```bash
uv run python -m unittest tests.test_memorial_renderer
```

Expected:

- fail because gas natural validator/renderer/fixture support does not exist yet, or
- fail because the template itself has a render defect

- [ ] **Step 3: Create the minimal valid gas natural fixture**

Create `tests/fixtures/gas_natural_base.json` with all required fields from the schema and realistic deterministic values.

Required sections:

```json
{
  "documento": {"data_atual": "10/04/2026"},
  "obra": {
    "numero_cadastro": "1234/2026",
    "construtora": "Exemplo Engenharia LTDA",
    "nome": "Residencial Exemplo",
    "localizacao": "Rua Exemplo, Recife/PE",
    "tipo_edificacao": "residencial",
    "tipologia": "torre unica",
    "qtd_apartamentos": 32,
    "qtd_lojas": 0,
    "qtd_restaurantes": 0
  },
  "crm": {"pavimento": "terreo"},
  "dimensionamento": {
    "qtd_fogao": 32,
    "qtd_aquecedor": 32,
    "qtd_churrasqueira": 0
  },
  "soma": {"qtd_pontos_de_utilizacao": 64},
  "ramal": {
    "primario_diametro": 32,
    "primario_material": "aco carbono",
    "primario_pavimento": "terreo"
  },
  "valvula": {"esfera_diametro": "32 mm"},
  "numero": {"prancha": "01/05"},
  "teto_ou_piso": "teto"
}
```

- [ ] **Step 4: If the render test fails because of template defects, stop and fix the template contract before backend rollout**

Allowed outcomes:

- proceed if the template renders correctly
- patch the template or notes if `valvula.esfera_diametro` or other placeholders are broken

- [ ] **Step 5: Re-run renderer tests**

Run:

```bash
uv run python -m unittest tests.test_memorial_renderer
```

Expected:

- gas natural renderer tests pass once the backend support for render is added in later tasks

### Task 2: JSON Generation Support

**Files:**
- Modify: `app/services/context_builder.py`
- Modify: `app/services/memorial_validator.py`
- Modify: `app/services/memorial_renderer.py`
- Modify: `app/services/pipeline.py`
- Modify: `tests/test_context_builder.py`
- Modify: `tests/test_memorial_validator.py`
- Modify: `tests/test_pipeline.py`
- Modify: `tests/test_memorial_renderer.py`

- [ ] **Step 1: Write the failing JSON-path tests**

Add tests for:

- `build_memorial_gas_natural_v1_context`
- `load_gas_natural_v1_schema`
- `validate_memorial_gas_natural_v1_context`
- `generate_memorial_gas_natural_v1`

Expected new test names:

```python
def test_gas_natural_fills_documento_data_atual_when_missing() -> None:
    ...

def test_load_gas_natural_v1_schema_returns_expected_contract() -> None:
    ...

def test_validate_memorial_gas_natural_v1_context_accepts_valid_fixture() -> None:
    ...

def test_generate_memorial_gas_natural_v1_builds_valid_context_and_renders() -> None:
    ...
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
uv run python -m unittest tests.test_context_builder tests.test_memorial_validator tests.test_pipeline tests.test_memorial_renderer
```

Expected:

- failures because gas natural functions are not defined yet

- [ ] **Step 3: Implement the minimal JSON path**

Add:

- `build_memorial_gas_natural_v1_context`
- `load_gas_natural_v1_schema`
- `validate_memorial_gas_natural_v1_context`
- `render_memorial_gas_natural_v1`
- `generate_memorial_gas_natural_v1`

Implementation rule:

- default only `documento.data_atual` if missing
- do not invent gas-specific derived values beyond deterministic defaults

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
uv run python -m unittest tests.test_context_builder tests.test_memorial_validator tests.test_pipeline tests.test_memorial_renderer
```

Expected:

- gas natural JSON path tests pass

### Task 3: JSON API Route

**Files:**
- Modify: `app/api/routes.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing API tests**

Add tests for:

- `POST /api/v1/memoriais/gas-natural` returning DOCX for valid payload
- invalid payload returning 400 with structured validation errors

- [ ] **Step 2: Run the API tests to verify they fail**

Run:

```bash
uv run python -m unittest tests.test_api
```

Expected:

- route-not-found or missing function failure

- [ ] **Step 3: Implement the JSON route**

Add route:

```text
POST /api/v1/memoriais/gas-natural
```

Behavior must match the existing electrical and telecom JSON routes:

- render to temporary DOCX
- return 400 on validation errors
- return 500 on render errors
- return attachment filename `memorial_gas_natural_v1.docx`

- [ ] **Step 4: Re-run the API tests**

Run:

```bash
uv run python -m unittest tests.test_api
```

Expected:

- gas natural JSON API tests pass

### Task 4: File Pipeline Skeleton And API Surface

**Files:**
- Modify: `app/services/pipeline_from_files.py`
- Modify: `app/api/routes.py`
- Modify: `tests/test_pipeline_from_files.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Write the failing file-pipeline tests**

Add tests for:

- gas natural uploaded-files wrapper calls ingestion and pipeline
- gas natural ingested-files pipeline wraps validation errors with `extraction_report`
- `POST /api/v1/memoriais/gas-natural/upload`
- `POST /api/v1/memoriais/gas-natural/from-files`

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
uv run python -m unittest tests.test_pipeline_from_files tests.test_api
```

Expected:

- failures because gas natural file flow functions/routes do not exist yet

- [ ] **Step 3: Implement the file skeleton**

Add:

- `generate_memorial_gas_natural_v1_from_ingested_files`
- `generate_memorial_gas_natural_v1_from_uploaded_files`
- upload route
- from-files route

Success criteria for this task:

- route accepts files
- pipeline performs ingestion and extraction mapping
- if context is incomplete, response includes structured validation errors and `extraction_report`
- render success is allowed when extraction is sufficient, but not required for every input yet

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
uv run python -m unittest tests.test_pipeline_from_files tests.test_api
```

Expected:

- file skeleton tests pass

### Task 5: Deterministic Gas Mapper And Coverage

**Files:**
- Modify: `app/services/extraction_mapper.py`
- Modify: `tests/test_extraction_mapper.py`
- Modify: `tests/test_pipeline_from_files.py`

- [ ] **Step 1: Write the failing mapper tests**

Add tests for:

- gas natural mapping of shared obra metadata from title block text
- gas natural coverage reporting for extractable versus pending fields
- gas natural partial context shape

Gas natural extractable fields should start conservative. Candidate first-pass fields:

- `obra.construtora`
- `obra.nome`
- `obra.localizacao`
- `obra.numero_cadastro`
- `obra.qtd_apartamentos`
- any gas-specific fields that can be justified by concrete text patterns from sample files

Gas natural pending fields should include contract fields not yet safely extractable by deterministic rules.

- [ ] **Step 2: Run the mapper tests to verify they fail**

Run:

```bash
uv run python -m unittest tests.test_extraction_mapper tests.test_pipeline_from_files
```

Expected:

- failures because gas natural mapping functions do not exist yet

- [ ] **Step 3: Implement conservative gas natural mapping**

Add:

- gas natural extractable field list
- gas natural pending field list
- `assess_gas_natural_extraction_coverage`
- `map_extraction_to_partial_gas_natural_context`

Implementation rule:

- do not fabricate gas-specific heuristics without evidence from real sample texts
- prefer a smaller reliable mapper plus pending fields over broad weak rules

- [ ] **Step 4: Re-run the mapper tests**

Run:

```bash
uv run python -m unittest tests.test_extraction_mapper tests.test_pipeline_from_files
```

Expected:

- deterministic gas mapper tests pass

### Task 6: Gas-Specific LLM Extraction Support

**Files:**
- Modify: `app/services/llm_extractor.py`
- Modify: `app/services/pipeline_from_files.py`
- Modify: `tests/test_llm_extractor.py`
- Modify: `tests/test_pipeline_from_files.py`

- [ ] **Step 1: Write the failing LLM tests**

Add tests for:

- gas natural schema defaults are `None`
- gas natural text-only input builder
- gas natural vision input builder
- gas natural single-file extraction wrapper
- gas natural merge wrapper
- gas natural pipeline path uses gas LLM as primary when `USE_LLM_EXTRACTION` is enabled

- [ ] **Step 2: Run the LLM-focused tests to verify they fail**

Run:

```bash
uv run python -m unittest tests.test_llm_extractor tests.test_pipeline_from_files
```

Expected:

- failures because gas natural LLM extraction contract does not exist yet

- [ ] **Step 3: Implement gas natural LLM extraction**

Add gas-specific:

- Pydantic extraction model
- extraction prompt
- merge prompt
- text-only input builder
- vision input builder
- per-file extraction wrapper
- merge wrapper
- top-level `extract_gas_natural_with_llm`

In `pipeline_from_files.py`, use the telecom-style pattern:

- gas LLM extraction as primary when enabled
- deterministic mapper fills only missing or `None` fields
- validation still decides whether final render is allowed

Important rule:

- keep gas natural extraction contract separate from future GLP
- do not build one generic gas LLM extractor that auto-classifies subtype

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
uv run python -m unittest tests.test_llm_extractor tests.test_pipeline_from_files
```

Expected:

- gas natural LLM extraction tests pass

### Task 7: Full API Regression And Real-File Validation

**Files:**
- Modify only if real-file validation reveals concrete issues

- [ ] **Step 1: Run the complete targeted memorial/API suite**

Run:

```bash
uv run python -m unittest tests.test_context_builder tests.test_memorial_validator tests.test_memorial_renderer tests.test_pipeline tests.test_extraction_mapper tests.test_llm_extractor tests.test_pipeline_from_files tests.test_api
```

Expected:

- all targeted gas-natural-adjacent tests pass

- [ ] **Step 2: Run the full repository suite if the above passes**

Run:

```bash
uv run python -m unittest discover -s tests
```

Expected:

- no regressions in electrical, telecom, session, or store flows

- [ ] **Step 3: Validate with real project files if available**

Use real gas natural PDFs or DOCX files if they exist in the repository or are provided later.

Expected outputs:

- identify which schema fields mapper-only can cover
- identify which fields consistently require LLM assistance
- refine mapper or LLM prompts based on concrete failures

## Risks and watchpoints

- the DOCX template may be defective even if the schema is correct
- `valvula.esfera_diametro` may fail because of DOCX run fragmentation
- adding gas-specific LLM extraction too late would delay real extraction quality
- adding gas-specific LLM extraction too early without mapper/validation scaffolding would make the track harder to debug
- broad extraction rules without sample evidence could create low-confidence false positives
- introducing generic gas abstractions now would increase scope and blur the GLP separation
- API naming and response behavior must stay consistent with existing memorial routes

## Test plan

Targeted commands during implementation:

```bash
uv run python -m unittest tests.test_context_builder
uv run python -m unittest tests.test_memorial_validator
uv run python -m unittest tests.test_memorial_renderer
uv run python -m unittest tests.test_pipeline
uv run python -m unittest tests.test_extraction_mapper
uv run python -m unittest tests.test_llm_extractor
uv run python -m unittest tests.test_pipeline_from_files
uv run python -m unittest tests.test_api
```

Final regression:

```bash
uv run python -m unittest discover -s tests
```

## Definition of done

This plan is complete only when:

1. gas natural template render is verified as safe or the template defect is fixed
2. gas natural JSON generation works end-to-end
3. gas natural JSON API route works and matches existing route behavior
4. gas natural upload and from-files routes exist and behave consistently with current memorial flows
5. from-files returns either rendered DOCX or structured validation feedback with `extraction_report`
6. deterministic gas mapper and coverage logic exist for conservative first-pass extraction
7. gas-specific LLM extraction support exists and is separate from future GLP
8. targeted tests pass
9. full regression suite passes
10. electrical and telecom behavior remain unchanged
