# GLP Extraction Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the GLP file-based pipeline produce canonical, deterministic memorial data by adding GLP-specific normalization, reconciliation, and conflict reporting before validation and rendering.

**Architecture:** Keep GLP LLM extraction as the required primary source, then add deterministic GLP mapper extraction and post-merge reconciliation for ramal fields, totals, and cross-sheet conflicts. The pipeline should continue only when deterministic rules resolve conflicts; otherwise it should stop with a structured report.

**Tech Stack:** Python, FastAPI, unittest, docxtpl pipeline, OCR text extraction, OpenAI structured extraction

---

### Task 1: Add failing reconciliation tests

**Files:**
- Modify: `tests/test_pipeline_from_files.py`
- Modify: `tests/test_api.py`
- Test: `tests/test_pipeline_from_files.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_glp_pipeline_prefers_table_sum_for_total_points(self) -> None:
    ...

def test_glp_pipeline_normalizes_ramal_location_fields(self) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_pipeline_from_files`
Expected: FAIL because GLP reconciliation logic does not exist yet

- [ ] **Step 3: Write minimal implementation**

```python
def _normalize_glp_context(context: dict[str, Any]) -> dict[str, Any]:
    ...

def _reconcile_glp_context(llm_context: dict[str, Any], mapper_context: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_pipeline_from_files`
Expected: PASS for the new GLP reconciliation cases

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline_from_files.py tests/test_api.py app/services/pipeline_from_files.py
git commit -m "test: add glp reconciliation regression coverage"
```

### Task 2: Add deterministic GLP quantitative extraction helpers

**Files:**
- Modify: `app/services/extraction_mapper.py`
- Modify: `tests/test_pipeline_from_files.py`
- Test: `tests/test_pipeline_from_files.py`

- [ ] **Step 1: Write the failing test**

```python
def test_glp_reconciliation_prefers_quantitative_table_sum(self) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_pipeline_from_files`
Expected: FAIL because mapper does not yet extract deterministic quantitative totals

- [ ] **Step 3: Write minimal implementation**

```python
def _extract_glp_quantitative_totals(text: str) -> dict[str, FieldExtraction]:
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_pipeline_from_files`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/extraction_mapper.py tests/test_pipeline_from_files.py
git commit -m "feat: add deterministic glp quantitative extraction"
```

### Task 3: Add GLP normalization and reconciliation in the file pipeline

**Files:**
- Modify: `app/services/pipeline_from_files.py`
- Modify: `tests/test_pipeline_from_files.py`
- Test: `tests/test_pipeline_from_files.py`

- [ ] **Step 1: Write the failing test**

```python
def test_glp_pipeline_fails_when_conflict_is_not_deterministically_resolved(self) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_pipeline_from_files`
Expected: FAIL because unresolved conflict handling is not implemented

- [ ] **Step 3: Write minimal implementation**

```python
def extract_glp_mapping_from_ingested_files(...):
    ...
    final_context, conflicts = _reconcile_glp_context(...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_pipeline_from_files`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/pipeline_from_files.py tests/test_pipeline_from_files.py
git commit -m "feat: reconcile glp extraction before validation"
```

### Task 4: Tighten GLP prompt guidance for canonical extraction

**Files:**
- Modify: `app/services/llm_extractor.py`
- Modify: `tests/test_llm_extractor.py`
- Test: `tests/test_llm_extractor.py`

- [ ] **Step 1: Write the failing test**

```python
def test_glp_prompt_mentions_quantitative_tables_and_mm_output(self) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_llm_extractor`
Expected: FAIL because prompt instructions are not specific enough

- [ ] **Step 3: Write minimal implementation**

```python
GLP_EXTRACTION_PROMPT = """..."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_llm_extractor`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/llm_extractor.py tests/test_llm_extractor.py
git commit -m "chore: tighten glp extraction prompt guidance"
```

### Task 5: Verify API behavior and real GLP generation

**Files:**
- Modify: `tests/test_api.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_post_memorial_glp_from_real_project_files_reports_unresolved_conflict(self) -> None:
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m unittest tests.test_api.ApiTests`
Expected: FAIL if conflict reporting path is not wired correctly

- [ ] **Step 3: Write minimal implementation**

```python
# wire extraction report / conflict handling through existing API error path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m unittest tests.test_api.ApiTests.test_post_memorial_glp_from_real_project_files_returns_docx_with_llm_context`
Expected: PASS for successful GLP generation with canonical data

- [ ] **Step 5: Commit**

```bash
git add tests/test_api.py app/api/routes.py app/services/pipeline_from_files.py
git commit -m "feat: expose glp conflict reporting through api"
```
