# LLM extraction eletrico PoC

## Goal

Create the smallest useful proof of concept for LLM-assisted extraction of
electrical memorial data from project PDFs using the OpenAI Responses API.

This PoC should stay isolated from the main backend flows and focus only on:

- sending one or more PDF files to an OpenAI model with PDF file input
- requesting Structured Outputs with a small JSON schema
- printing or saving the resulting structured JSON for manual inspection

## Why this change is needed

- The current deterministic extractor + regex mapper can run the pipeline, but
  real project PDFs still produce weak or incorrect extractions for critical
  fields such as `obra.construtora`, `obra.nome`, `obra.localizacao`, and
  several required schema fields.
- The review-session flow proves that the system architecture is sound, but the
  extraction layer is now the main bottleneck for generation quality.
- An isolated PoC is the lowest-risk way to validate whether GPT with PDF
  inputs can improve extraction quality before any integration with the main
  pipeline.
- This matters now because the team already has real PDFs, review-session UX,
  and validation feedback to judge whether the LLM output is materially better
  than the current mapper.

## Scope

### In scope

- Inspect current extraction/mapping structures and place a standalone PoC in
  the repository.
- Create a small extraction schema focused on a handful of useful memorial
  fields.
- Use the OpenAI Responses API.
- Use PDF file input via uploaded file IDs.
- Use Structured Outputs / JSON schema response format.
- Build a script that accepts local PDF paths, calls the API, and prints or
  saves the structured JSON.
- Keep the PoC outside the main API routes and service pipelines.

### Out of scope

- Integrating LLM extraction into `app/api/routes.py`.
- Replacing `project_extractor.py` or `extraction_mapper.py`.
- Changing review-session behavior.
- Using the LLM to generate the final memorial DOCX.
- Prompt chaining, retries, evaluator loops, or multi-step agent flows.
- OCR, image preprocessing, or complex post-processing.
- Deep schema coverage of the full memorial contract.

## Current state

- The current extraction path is fully deterministic:
  - `app/services/file_ingestion.py`
  - `app/services/project_extractor.py`
  - `app/services/extraction_mapper.py`
  - `app/services/context_builder.py`
  - `app/services/memorial_validator.py`
  - `app/services/memorial_renderer.py`
- `project_extractor.py` currently extracts text from PDF via PyMuPDF and DOCX
  via `python-docx`, returning:
  - `raw_text`
  - `source_files`
  - `signals`
- `extraction_mapper.py` maps text into a partial memorial context and emits:
  - `FieldExtraction`
  - `ExtractionReport`
  - `MappingResult`
- The current mapper already reveals extraction pain points from real PDFs:
  carimbo confusion, label confusion, weak evidence on inferred
  `nao_inclusos.*`, and missing required fields such as `energia.tem_subestacao`
  and parts of `mt`, `instalacao`, `gerador`, and `obra`.
- The repository currently has no OpenAI integration:
  - no `openai` package in `requirements.txt`
  - no scripts under `scripts/` besides `scripts/test_render_eletrico.py`
- The docs and codebase already support a plan-driven incremental workflow in
  `docs/plans/`.
- Official OpenAI docs confirm the pieces needed for this PoC:
  - PDF inputs are supported in Responses by uploading files to `/v1/files` with
    `purpose="user_data"` and then passing `input_file` with `file_id`
    ([File inputs guide](https://developers.openai.com/api/docs/guides/file-inputs))
  - Structured Outputs are supported through JSON schema-based structured output
    in Responses-compatible models
    ([Structured output guide](https://platform.openai.com/docs/guides/structured-outputs/json-mode?api-mode=responses))
  - Modern models support image input and Structured Outputs in the Responses
    API ([Models docs](https://developers.openai.com/api/docs/models))

## Constraints to preserve

- Do not change the current production/API extraction path.
- Do not change template or schema behavior.
- Do not use the LLM to generate the final memorial text.
- Keep the PoC as a standalone script with local, explicit execution.
- Prefer a small extraction schema over a premature full memorial schema.
- Keep the output JSON shape explicit and inspectable.
- Avoid introducing abstractions that imply production integration before the
  team validates the approach.

## Milestones

1. Confirm PoC placement and current extraction gaps
2. Define a small, useful extraction schema
3. Design the standalone script contract
4. Implement OpenAI Responses call with file upload + structured output
5. Add minimal docs/tests/manual verification guidance

## Detailed implementation notes

### Milestone 1

- Files:
  - `scripts/`
  - `app/services/extraction_mapper.py`
  - `tests/test_extraction_mapper.py`
  - `requirements.txt`
- Intended change:
  - Keep the PoC in `scripts/`, not `app/services/`, because this stage is an
    experiment and should not suggest production integration.
  - Use the current mapper gaps to choose the first extraction targets.

### Milestone 2

- Files:
  - new script-local schema declaration inside the PoC script, or a tiny helper
    under `app/schemas/` only if reuse becomes obviously useful
- Intended change:
  - Start with a deliberately small schema that is useful for review and easy
    to judge against real PDFs.
  - Recommended first schema:
    - `obra.construtora: string | null`
    - `obra.nome: string | null`
    - `obra.localizacao: string | null`
    - `obra.numero_cadastro: string | null`
    - `energia.tem_subestacao: boolean | null`
    - `energia.tipo_subestacao: string | null`
    - `aterramento.tipo_sistema: string | null`
    - `mt.tensao_kv: number | null`
    - `mt.secao_cabo_mm2: number | null`
    - `gerador.tipo_atendimento: string | null`
  - Include one metadata field for model self-reporting:
    - `observacoes: string | null`
  - Keep every field optional/null-friendly so the PoC measures extraction
    quality instead of failing on completeness.

### Milestone 3

- Files:
  - `scripts/llm_extract_eletrico_poc.py`
- Intended change:
  - The script should accept:
    - one or more local PDF paths as positional args
    - optional `--model`
    - optional `--output path.json`
  - Use environment variable `OPENAI_API_KEY`.
  - Upload each PDF with the Files API using `purpose=\"user_data\"`.
  - Call `client.responses.create(...)` with:
    - `model=...`
    - `input=[{role: \"user\", content: [input_file..., input_text...]}]`
    - structured output via JSON schema response format
  - Print JSON to stdout by default.
  - Save JSON to file if `--output` is provided.
  - For the first version, file cleanup on OpenAI side can be manual/not
    implemented if the SDK flow is simpler; if easy, delete uploaded files at
    the end.

### Milestone 4

- Files:
  - `scripts/llm_extract_eletrico_poc.py`
  - `requirements.txt`
- Intended change:
  - Add `openai` dependency.
  - Use the official Python SDK, not raw `requests`, unless the SDK blocks a
    needed capability.
  - Prefer uploaded file IDs over base64 embedding because:
    - cleaner request payloads
    - closer to future backend integration
    - aligned with the official file-input guidance
  - Model choice:
    - default to a current multimodal Responses model that supports Structured
      Outputs and image input
    - choose a conservative default in code after checking current model names
      during implementation; likely `gpt-5.4` or a lower-cost multimodal model
      if sufficient
  - Prompt shape:
    - tell the model it is extracting structured engineering data from Brazilian
      electrical project PDFs
    - instruct it to avoid guessing
    - return `null` when not confident
    - focus only on the requested fields
    - consider diagrams, title blocks, and utility sheets as evidence

### Milestone 5

- Files:
  - `README.md` only if a very small usage note is warranted
  - possibly `tests/` only if a low-cost unit test around schema assembly or
    CLI argument validation is justified
- Intended change:
  - Prefer manual verification for the API call itself in this phase.
  - If adding automated tests, keep them local and cheap:
    - test schema-building helper
    - test CLI argument validation
    - test output serialization without hitting the network

## Risks and watchpoints

- PDF inputs send both extracted text and page images into model context, which
  can be significantly more expensive than plain text extraction.
- Model behavior may improve extraction quality for title blocks and diagrams,
  but can still hallucinate missing values if the prompt/schema is too strict.
- Over-scoping the schema too early would make the PoC look worse than it is by
  forcing completeness before extraction quality is understood.
- Adding the PoC inside `app/services/` would create pressure to integrate an
  unvalidated path into production flows.
- Model/version naming is time-sensitive; use the current docs at
  implementation time instead of hard-coding assumptions from this plan.
- The Python SDK surface for structured output in Responses may differ slightly
  from older examples; verify the exact call shape during implementation.

## Test plan

### Manual verification

1. Run the script with one known project PDF.
2. Run the script with the Energisa sheet plus one architectural/electrical
   sheet.
3. Inspect whether the JSON improves on the current deterministic mapper for:
   - `obra.construtora`
   - `obra.nome`
   - `obra.localizacao`
   - `energia.tem_subestacao`
   - `mt.tensao_kv`
4. Compare output against the current `partial_context` from review-session
   extraction.

### Targeted automated checks

If lightweight helper functions are added:

```bash
.venv/bin/python -m unittest tests.test_llm_extract_eletrico_poc
```

### Regression safety

- No main regression suite is required for the initial PoC if only a new script
  and optional isolated tests are added.
- If shared modules are touched, run the relevant existing tests plus:

```bash
.venv/bin/python -m unittest discover -s tests
```

## Definition of done

- A standalone PoC script exists outside the main API flow.
- The script accepts local PDFs and produces structured JSON using the OpenAI
  Responses API.
- The PoC uses uploaded PDF file inputs and Structured Outputs.
- The initial extraction schema remains intentionally small and useful.
- The current backend behavior remains unchanged.
- The plan file is updated with progress if implementation proceeds.

## Progress log

- 2026-03-27 00:00: inspected current extraction, mapping, scripts, and plan
  conventions in the repository.
- 2026-03-27 00:00: confirmed there is no existing OpenAI integration and that
  `scripts/` is the safest place for an isolated PoC.
- 2026-03-27 00:00: reviewed official OpenAI documentation for PDF file inputs,
  file uploads, and structured outputs in Responses.
- 2026-03-27 00:01: created `scripts/llm_extract_eletrico_poc.py` as a
  standalone CLI that accepts one or more local PDFs and requests structured
  extraction from the Responses API.
- 2026-03-27 00:02: implemented a small null-friendly extraction schema focused
  on high-value electrical memorial fields and added optional JSON output file
  support.
- 2026-03-27 00:03: added `openai` to `requirements.txt` and documented quick
  script usage in the script header.
- 2026-03-27 00:04: performed minimal local verification through import/syntax
  checks and CLI help output without integrating the PoC into the main backend.
- 2026-03-27 00:05: confirmed the local SDK exposes `responses.parse`; no real
  API call was executed because `OPENAI_API_KEY` was not configured in the
  current environment.

## Final outcome

- Changed:
  - Added a standalone PoC script in `scripts/llm_extract_eletrico_poc.py`
  - Added the `openai` dependency to `requirements.txt`
  - Implemented PDF upload + Responses API call + Structured Outputs using a
    small, useful memorial extraction schema
  - Added optional JSON file output and conservative remote-file cleanup

- Not changed:
  - API routes
  - review-session flow
  - main extraction/mapping pipeline
  - rendering or validation behavior

- Verification performed:
  - CLI help output
  - Python syntax/import check for the script
  - local dependency installation in `.venv` for the PoC
  - confirmation that the installed SDK exposes `responses.parse`
  - no live API call in this implementation pass because `OPENAI_API_KEY` was
    not present in the environment

- Follow-ups:
  - compare PoC output against real project PDFs and current review-session
    `partial_context`
  - decide whether the PoC should evolve into a review-session assistant path,
    not a replacement for deterministic final rendering
