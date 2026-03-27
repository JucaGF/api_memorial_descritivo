# AGENTS.md

Instructions for code agents working in this repository.

Read this file before making changes.

## Project focus

This repository implements an API for automatic generation of engineering memorial documents from technical project files.

Current focus: **memorial elétrico v1**.

The system already includes:

- DOCX template + JSON schema
- JSON-based generation flow
- file ingestion flow
- generation from files
- review-session flow with background extraction
- session persistence in filesystem
- optional session persistence in Supabase
- automated tests across API, stores, mapper, pipelines, and rendering

Do not treat this repository as an early prototype. It is an existing backend in active evolution.

## Core rules

Always preserve these rules:

1. The **DOCX template** is the source of truth for the final document.
2. The **JSON schema** defines the data contract required for rendering.
3. Final memorial generation must remain **deterministic**.
4. Do **not** use LLMs to generate the final memorial document.
5. Validate data before rendering.
6. Prefer **small, localized changes** over broad refactors.
7. Preserve existing API behavior unless the task explicitly requires changing it.

## Main areas of the codebase

Work from the existing structure, not from a hypothetical future architecture.

- `app/api/`  
  HTTP routes and orchestration of exposed flows

- `app/schemas/`  
  API and internal data contracts

- `app/services/`  
  Business logic, including ingestion, pipelines, mapping, session handling, validation, rendering, and optional Supabase integration

- `templates/eletrico/v1/`  
  Memorial template, schema, and notes

- `tests/`  
  Automated tests

- `migrations/`  
  Persistence-related migrations

## Key flows

### 1. JSON generation

Use when the memorial context is already structured.

Expected behavior:

- validate context
- render DOCX
- return final document

### 2. File ingestion

Use when uploaded files must be prepared for extraction/generation.

### 3. Generation from files

Expected behavior:

- ingest files
- extract relevant information
- map extraction into memorial context
- validate context
- render DOCX

### 4. Review sessions

Expected behavior:

- create session
- run extraction in background
- persist partial context and extraction report
- allow manual corrections
- merge corrections into context
- generate final document from reviewed context

When changing review-session code, preserve consistency across:

- route behavior
- background task responsibility
- session store behavior
- filesystem and Supabase backends

## Template and schema

Primary files:

- `templates/eletrico/v1/template.docx`
- `templates/eletrico/v1/schema.json`

Rules:

- always keep template and schema coherent
- do not change template behavior without checking schema impact
- do not change schema without checking template and tests
- rendered DOCX must not contain unresolved Jinja placeholders

## Extraction and mapping

Extraction may use parsing, OCR, heuristics, vision, or LLM assistance, but the output used for final rendering must still conform to the schema-driven contract.

When changing extraction or mapping:

- prefer incremental changes
- preserve pipeline compatibility
- update tests for changed rules
- avoid making weak inferences look like high-confidence data

## Sessions and persistence

The review-session flow is a critical part of the current system.

When changing session-related code:

- preserve current API behavior when possible
- keep filesystem and Supabase behavior aligned
- handle expiration, cleanup, and background-task ownership carefully
- avoid introducing dead states or ambiguous status transitions

## How to work

Before changing code:

1. Read `README.md`
2. Read this `AGENTS.md`
3. Read `docs/PLANS.md`
4. Inspect the files directly related to the task
5. Understand the current behavior before proposing changes

For simple tasks:

- make the smallest correct change
- update relevant tests
- run targeted tests

For medium or risky tasks:

1. inspect current behavior first
2. write a short implementation plan
3. then make the change
4. run relevant tests

For large tasks or refactors:

- use a plan document before implementation
- break work into milestones
- keep scope controlled

## Testing

Run relevant tests for the area you changed.

Common commands:

```bash
python -m unittest discover -s tests
python -m unittest tests.test_api
python -m unittest tests.test_session_store
python -m unittest tests.test_supabase_session_store
```

If you change:

- API behavior: run API tests
- session persistence: run store tests
- extraction or mapping: run related mapper/pipeline tests
- template/render logic: run rendering-related tests

Do not consider the task complete without running relevant tests.

## Avoid

Do not:

- remove schema validation
- use LLMs to generate the final memorial
- change template and schema incoherently
- create unnecessary abstractions
- modify unrelated parts of the codebase
- make large refactors when a focused change is enough
- assume behavior without checking the code
- modify files outside the repository

## Definition of done

A task is done only when:

- the requested behavior is correctly implemented
- the change is consistent with the current architecture
- relevant tests pass
- the scope stayed controlled
- the final code remains readable and maintainable
- the summary of changes is clear and concrete

## Current engineering priorities

When multiple implementation paths are possible, prefer the one that improves:

1. operational robustness of existing flows
2. clarity of review-session contracts
3. consistency between filesystem and Supabase
4. stronger tests
5. reduced duplication in file-based pipelines
6. incremental improvements to extraction/mapping
