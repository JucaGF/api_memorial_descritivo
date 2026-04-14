# AGENTS.md

Instructions for coding agents working in this repository.

Read this file before making changes.

## 1) Mission and project state

This repository is a production-oriented backend for automatic generation of engineering memorial documents from technical project files.

Current operational focus:

- memorial eletrico v1 (end-to-end generation and review-session flow)

Secondary track in progress:

- memorial telecom v1 (schema/notes currently present; full generation flow still evolving)

Treat the codebase as an actively evolving system, not as a greenfield prototype.

## 2) Instruction hierarchy (follow in this order)

When instructions conflict, use this precedence:

1. Direct user request for the current task
2. System/developer runtime instructions
3. This AGENTS.md
4. Local implementation patterns in the touched modules

If a user request conflicts with a hard safety/contract rule below, keep the contract and explain the limitation.

## 3) Non-negotiable system rules

Always preserve these constraints:

1. The DOCX template is the source of truth for final document structure.
2. The JSON schema is the data contract for rendering.
3. Final memorial generation must remain deterministic.
4. Do not use LLM output as final memorial content generation.
5. Validate data before rendering.
6. Prefer small and localized changes over broad refactors.
7. Preserve existing API behavior unless the task explicitly requires behavior change.
8. Rendered DOCX must not contain unresolved Jinja placeholders.

## 4) Repository map

Primary areas:

- app/api/: route handlers and HTTP orchestration
- app/schemas/: API/internal contracts
- app/services/: ingestion, extraction, mapping, pipelines, sessions, validation, rendering
- templates/eletrico/v1/: template + schema + notes
- templates/telecom/v1/: schema + notes (contract track)
- tests/: unit/integration coverage
- migrations/: persistence changes

## 5) Core flows to protect

### 5.1 JSON generation flow

Use when context is already structured.
Expected behavior:

- validate context
- render DOCX
- return final document

### 5.2 File ingestion flow

Use when uploaded files must be prepared for extraction/generation.

### 5.3 Generation-from-files flow

Expected behavior:

- ingest files
- extract information
- map extraction into memorial context
- validate context
- render DOCX

### 5.4 Review-session flow

Expected behavior:

- create session
- execute extraction in background
- persist partial context and extraction report
- allow manual corrections
- merge corrections into context
- generate final document from reviewed context

When changing review sessions, preserve consistency across:

- route behavior
- background task ownership
- session store behavior
- filesystem and Supabase backends

## 6) Vibe coding operating mode (how to execute work)

Use fast, safe iteration loops:

1. Understand current behavior in code before editing.
2. Make the smallest useful change.
3. Run the narrowest relevant tests immediately.
4. Inspect failures and fix with focused edits.
5. Expand validation only after targeted tests pass.

Execution principles:

- Favor clarity over clever abstractions.
- Favor concrete evidence (tests/output) over assumptions.
- Keep changes reversible and easy to review.
- Do not mix unrelated refactors with requested behavior changes.

## 7) Required workflow before editing

Before changing code:

1. Read README.md.
2. Read this AGENTS.md.
3. Read docs/PLANS.md.
4. Inspect files directly related to the task.
5. Identify existing behavior and relevant tests.

For medium/high-risk tasks:

- write a short plan before implementation
- define what must not break
- validate each milestone with tests

## 8) Change scope guidelines

For simple tasks:

- implement minimal correct change
- update/add relevant tests only
- run targeted test module(s)

For medium/risky tasks:

- inspect behavior first
- plan briefly
- implement incrementally
- run targeted tests + nearby regression tests

For large tasks/refactors:

- use a plan file in docs/plans/
- split into milestones
- keep compatibility constraints explicit

## 9) Testing policy (mandatory)

Do not consider a task complete without running relevant tests.
use uv venv

Common commands:

```bash
python -m unittest discover -s tests
python -m unittest tests.test_api
python -m unittest tests.test_session_store
python -m unittest tests.test_supabase_session_store
```

Minimum required by change type:

- API behavior changes: run tests.test_api
- session persistence changes: run tests.test_session_store and tests.test_supabase_session_store
- extraction/mapping changes: run mapper/pipeline-related tests
- render/template/validation changes: run memorial renderer/validator tests
- cross-flow changes: run full suite (discover -s tests)

## 10) Template and schema evolution rules

If touching template/schema-related logic:

- keep template and schema coherent
- do not change template behavior without schema impact check
- do not change schema without template and test impact check
- keep rendering deterministic and contract-driven

## 11) Extraction and mapping rules

Extraction can use parsing/OCR/heuristics/vision/LLM assistance, but:

- output used for final rendering must conform to schema contract
- do not present low-confidence inference as high-confidence fact
- preserve pipeline compatibility when evolving mapping
- update tests for changed mapping/extraction rules

## 12) Session and persistence rules

Review-session behavior is critical.
When changing session code:

- preserve API contract whenever possible
- keep filesystem and Supabase behavior aligned
- handle expiration and cleanup explicitly
- avoid ambiguous or dead status transitions

## 13) Avoid

Do not:

- remove schema validation
- use LLMs to generate final memorial document content
- change template and schema incoherently
- introduce unnecessary abstractions
- modify unrelated parts of codebase
- assume behavior without reading code
- modify files outside repository scope

## 14) Definition of done

A task is done only when:

1. requested behavior is correctly implemented
2. architecture/contracts are preserved
3. relevant tests pass
4. scope remained controlled
5. code is readable and maintainable
6. changes and validation were clearly summarized

## 15) Engineering priorities for trade-off decisions

When multiple valid paths exist, prefer what improves:

1. robustness of existing operational flows
2. clarity of review-session contracts
3. consistency between filesystem and Supabase backends
4. test strength and confidence
5. duplication reduction in file-based pipelines
6. incremental quality gains in extraction/mapping
