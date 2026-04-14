# Frontend API Reference

## Purpose

This document describes the current HTTP API exposed by the backend in a frontend-oriented way.

It is intended to help the frontend team implement:

- direct memorial generation from JSON
- file upload flows
- generation from uploaded files
- electric review-session flow
- download handling for generated DOCX files
- validation and extraction error handling in the UI

This document reflects the current route behavior implemented in:

- `app/api/routes.py`
- `app/schemas/file_ingestion.py`
- `app/schemas/review_session.py`

## Base Characteristics

### Base path

All routes are under:

```text
/api/v1
```

### Main response types

The API returns one of these broad categories:

- JSON success payload
- JSON error payload
- DOCX file download

### DOCX content type

When a memorial is generated successfully, the API returns a file response with:

```text
application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

The frontend should treat this as a binary download or Blob.

### Route families

There are 4 main memorial families currently exposed:

- `eletrico`
- `telecom`
- `gas-natural`
- `glp`

And one review-session flow currently exposed only for:

- `eletrico`

## Recommended Frontend Architecture

For the frontend, the cleanest mental model is to split the interface into 4 flow types:

1. JSON generation
2. File upload only
3. Generation from files
4. Review session

That maps directly to the route design.

## Common Error Shapes

### 1. Validation error

Returned when the generated or submitted memorial context is invalid.

HTTP status:

```text
400
```

Shape:

```json
{
  "detail": "Payload invalido para o memorial eletrico v1.",
  "errors": [
    {
      "path": "$.obra",
      "message": "'tipo_edificacao' is a required property",
      "validator": "required"
    }
  ]
}
```

Sometimes it also includes `extraction_report`:

```json
{
  "detail": "Payload invalido para o memorial GLP v1.",
  "errors": [
    {
      "path": "$.soma.qtd_pontos_de_utilizacao",
      "message": "Conflito GLP em qtd_pontos_de_utilizacao sem resolucao deterministica.",
      "validator": "glp_conflict"
    }
  ],
  "extraction_report": {
    "filled": [],
    "missing": [],
    "pending": [],
    "evidence": {},
    "conflicts": []
  }
}
```

Frontend recommendation:

- always render `detail`
- render `errors[]` as a list
- if present, expose `extraction_report` in a collapsible debug panel

### 2. File/extraction error

Returned when upload or extraction cannot proceed.

HTTP status:

```text
400
```

Shape:

```json
{
  "detail": "Extensao nao suportada para extracao: .txt."
}
```

Frontend recommendation:

- show this as a form-level error
- do not expect `errors[]` in this shape

### 3. Render/internal generation error

Returned when the backend fails after validation during render.

HTTP status:

```text
500
```

Shape:

```json
{
  "detail": "Falha ao renderizar o memorial eletrico v1.",
  "error": "..."
}
```

Frontend recommendation:

- show a generic failure state
- optionally log `error` in internal tooling only

### 4. Session conflict / workflow state error

Used by review-session endpoints.

HTTP status:

```text
409
```

Shape example:

```json
{
  "detail": "Extração ainda em andamento."
}
```

or:

```json
{
  "detail": "Sessão em status 'processing' não pode gerar memorial."
}
```

Frontend recommendation:

- use for disabled actions or banner messages
- do not treat as fatal transport error

### 5. Not found

HTTP status:

```text
404
```

Shape:

```json
{
  "detail": "Sessão não encontrada."
}
```

## Binary Response Handling

All successful memorial generation routes return DOCX directly, not JSON.

Frontend implementation recommendation:

- send request
- if `content-type` is DOCX, create Blob and download
- if `content-type` is JSON, parse and render the error body

Pseudo-flow:

```ts
const response = await fetch(url, options);
const contentType = response.headers.get("content-type") ?? "";

if (contentType.includes("application/vnd.openxmlformats-officedocument.wordprocessingml.document")) {
  const blob = await response.blob();
  // download blob
} else {
  const body = await response.json();
  // show error
}
```

## Route Reference

---

## 1. Direct JSON Generation Routes

These routes accept a full memorial payload as JSON and return a DOCX if valid.

### 1.1 POST `/api/v1/memoriais/eletrico`

Generate electric memorial from structured JSON.

Request body:

- JSON object matching the electric memorial schema

Success:

- `200`
- DOCX file
- filename: `memorial_eletrico_v1.docx`

Validation failure:

- `400`
- validation JSON body

Render failure:

- `500`
- render error JSON body

Suggested UI:

- large form or JSON-backed wizard
- submit button downloads DOCX on success

### 1.2 POST `/api/v1/memoriais/telecom`

Generate telecom memorial from structured JSON.

Request body:

- JSON object matching the telecom memorial schema

Success:

- `200`
- DOCX file
- filename: `memorial_telecom_v1.docx`

Errors:

- same shape as electric route

### 1.3 POST `/api/v1/memoriais/gas-natural`

Generate natural gas memorial from structured JSON.

Request body:

- JSON object matching the gas natural memorial schema

Success:

- `200`
- DOCX file
- filename: `memorial_gas_natural_v1.docx`

Errors:

- same validation/render pattern

### 1.4 POST `/api/v1/memoriais/glp`

Generate GLP memorial from structured JSON.

Request body:

- JSON object matching the GLP memorial schema

Success:

- `200`
- DOCX file
- filename: `memorial_glp_v1.docx`

Errors:

- same validation/render pattern

Frontend note:

- for all direct JSON routes, the frontend does not need multipart upload
- plain `application/json` is sufficient

---

## 2. Upload-Only Routes

These routes only validate/ingest uploaded files and return file metadata.

They do not generate a memorial.

### Allowed input style

All upload routes accept:

- multipart form-data
- repeated field name `files`

Frontend should send:

```text
files=<file1>
files=<file2>
files=<file3>
```

### File metadata success shape

Response model:

```json
{
  "files": [
    {
      "filename": "projeto.pdf",
      "content_type": "application/pdf",
      "extension": ".pdf",
      "size_bytes": 123456
    }
  ]
}
```

### 2.1 POST `/api/v1/memoriais/eletrico/upload`

Success:

- `200`
- `FileIngestionResponse`

Failure:

- `400`
- `{ "detail": "..." }`

### 2.2 POST `/api/v1/memoriais/telecom/upload`

Same behavior as electric upload.

### 2.3 POST `/api/v1/memoriais/gas-natural/upload`

Same behavior as electric upload.

### 2.4 POST `/api/v1/memoriais/glp/upload`

Same behavior as electric upload.

Suggested UI use:

- “validate files before continuing”
- file review step
- show metadata table before generation

---

## 3. Generation From Files Routes

These routes accept project files directly and attempt full memorial generation.

They:

1. ingest files
2. extract project data
3. map into memorial context
4. validate context
5. render DOCX

All use multipart form-data with repeated `files`.

### 3.1 POST `/api/v1/memoriais/eletrico/from-files`

Success:

- `200`
- DOCX file
- filename: `memorial_eletrico_v1.docx`

Possible failures:

- `400` validation body with `errors[]`
- `400` extraction/file error with `detail`
- `500` render failure

### 3.2 POST `/api/v1/memoriais/telecom/from-files`

Success:

- `200`
- DOCX file
- filename: `memorial_telecom_v1.docx`

Failures:

- same general pattern as electric

### 3.3 POST `/api/v1/memoriais/gas-natural/from-files`

Success:

- `200`
- DOCX file
- filename: `memorial_gas_natural_v1.docx`

Failures:

- validation body
- extraction/file body
- render failure body

### 3.4 POST `/api/v1/memoriais/glp/from-files`

Success:

- `200`
- DOCX file
- filename: `memorial_glp_v1.docx`

Important current behavior:

- GLP from-files depends on LLM extraction being enabled on the backend
- validation failures may include `extraction_report`
- GLP can also return extraction conflict information inside `extraction_report.conflicts`

Example validation/conflict body:

```json
{
  "detail": "Payload invalido para o memorial GLP v1.",
  "errors": [
    {
      "path": "$.soma.qtd_pontos_de_utilizacao",
      "message": "Conflito GLP em qtd_pontos_de_utilizacao sem resolucao deterministica.",
      "validator": "glp_conflict"
    }
  ],
  "extraction_report": {
    "filled": ["obra.nome"],
    "missing": [],
    "pending": [],
    "evidence": {
      "obra.nome": {
        "value": "MAKAI",
        "rule": "carimbo_line_before_company",
        "evidence": "'MAKAI' — linha anterior a ...",
        "confidence": "high"
      }
    },
    "conflicts": [
      {
        "type": "glp_total_points_conflict",
        "status": "resolved"
      }
    ]
  }
}
```

Frontend recommendation for all `/from-files` routes:

- use upload UI with multi-file selection
- on submit, expect either binary DOCX or JSON error
- if JSON has `extraction_report`, show advanced debug panel

---

## 4. Electric Review Session Flow

This flow currently exists only for the electric memorial.

It is designed for:

- async extraction
- manual correction before final generation

This is the most frontend-rich flow in the API.

### Session statuses observed in backend/tests

Frontend should be prepared for at least:

- `processing`
- `pending_review`
- `completed`
- `failed`

### 4.1 POST `/api/v1/memoriais/eletrico/sessoes`

Create a new electric review session and start extraction in the background.

Request:

- multipart form-data
- repeated `files`

Success:

- `202`
- response model `SessionCreatedResponse`

Shape:

```json
{
  "session_id": "test-session-id",
  "status": "processing"
}
```

Frontend behavior:

- after creating a session, redirect to a review page keyed by `session_id`
- begin polling the session detail endpoint

### 4.2 GET `/api/v1/memoriais/eletrico/sessoes/{session_id}`

Fetch current session state.

Success:

- `200`
- response model `SessionStateResponse`

Shape:

```json
{
  "session_id": "abc-123",
  "status": "pending_review",
  "created_at": "2026-04-14T10:00:00+00:00",
  "expires_at": "2026-04-15T10:00:00+00:00",
  "partial_context": {},
  "extraction_report": {
    "filled": [],
    "missing": [],
    "pending": [],
    "evidence": {}
  },
  "corrections": {},
  "error": null
}
```

Special note:

- `extraction_report` may also temporarily be `{}` for compatibility while processing

Not found:

- `404`
- `{ "detail": "Sessão não encontrada." }`

Frontend behavior:

- poll while `status === "processing"`
- once `pending_review`, render correction UI from `partial_context`
- show extraction progress using `filled`, `missing`, `pending`

### 4.3 PATCH `/api/v1/memoriais/eletrico/sessoes/{session_id}/contexto`

Update manual corrections for a session.

Request body model:

```json
{
  "corrections": {
    "obra": {
      "tipologia": "Vertical"
    }
  }
}
```

Behavior:

- backend deep-merges corrections with existing corrections
- does not replace the whole object blindly

Success:

- `200`
- full updated `SessionStateResponse`

Conflict:

- `409`
- if extraction is still processing

Frontend behavior:

- treat this like save-draft of manual corrections
- sending partial nested corrections is valid

### 4.4 POST `/api/v1/memoriais/eletrico/sessoes/{session_id}/gerar`

Generate final electric memorial from:

- extracted partial context
- merged manual corrections

Success:

- `200`
- DOCX file

Not found:

- `404`

Invalid session status:

- `409`

Validation failure:

- `400`
- same validation error shape as direct generation routes

Frontend behavior:

- show “Generate final memorial” button only when session is ready
- if validation fails, render field/path errors and keep user on review page

## Frontend Data Models

These are the useful frontend-side TypeScript-style interfaces derived from the backend.

### File upload metadata

```ts
type UploadedFileResponse = {
  filename: string;
  content_type: string;
  extension: string;
  size_bytes: number;
};

type FileIngestionResponse = {
  files: UploadedFileResponse[];
};
```

### Validation issue

```ts
type ValidationIssue = {
  path: string;
  message: string;
  validator: string;
};
```

### Extraction evidence

```ts
type FieldExtractionResponse = {
  value: unknown;
  rule: string;
  evidence?: string | null;
  confidence: string;
};
```

### Extraction report

```ts
type ExtractionReportResponse = {
  filled: string[];
  missing: string[];
  pending: string[];
  evidence: Record<string, FieldExtractionResponse>;
  conflicts?: unknown[];
};
```

### Session created

```ts
type SessionCreatedResponse = {
  session_id: string;
  status: string;
};
```

### Session state

```ts
type SessionStateResponse = {
  session_id: string;
  status: string;
  created_at: string;
  expires_at: string;
  partial_context: Record<string, unknown>;
  extraction_report: ExtractionReportResponse | Record<string, unknown>;
  corrections: Record<string, unknown>;
  error?: string | null;
};
```

### Generic validation error body

```ts
type ApiValidationError = {
  detail: string;
  errors: ValidationIssue[];
  extraction_report?: ExtractionReportResponse;
};
```

### Generic detail error body

```ts
type ApiDetailError = {
  detail: string;
};
```

### Render/internal error body

```ts
type ApiRenderError = {
  detail: string;
  error: string;
};
```

## Suggested UI Screens

### 1. Direct memorial generation screen

Use for:

- electric
- telecom
- gas natural
- GLP

UI pieces:

- structured form or imported JSON
- submit
- download result
- error panel for `errors[]`

### 2. Multi-file upload/generation screen

Use for:

- electric from files
- telecom from files
- gas natural from files
- GLP from files

UI pieces:

- drag-and-drop multi-file uploader
- file list with filename/size/type
- generate button
- extraction/validation error panel

### 3. Electric review session screen

UI pieces:

- create session from files
- polling state
- partial context editor
- corrections editor
- extraction report panel
- final generate button

## Important Product Notes For Frontend

### 1. Success may be binary, failure may be JSON

The same route can return:

- binary DOCX on success
- JSON on failure

This must be handled explicitly in the client.

### 2. Validation errors are field-like, but not always form-field aligned

The backend uses JSON-path-style `path` values like:

- `$.obra`
- `$.crm`
- `$.soma.qtd_pontos_de_utilizacao`

Frontend should support:

- field-level mapping when possible
- generic error list fallback when not

### 3. Extraction report is valuable for advanced UI

Especially for:

- review session
- generation from files
- GLP conflict debugging

Even if not shown to all users, it is useful for:

- admin/debug view
- expandable “technical details” panel

### 4. Review session exists only for electric right now

Do not build generic review-session UI for telecom/gas unless backend adds those routes.

### 5. GLP from-files can surface conflict information

The frontend should be prepared to show:

- validation errors
- extraction evidence
- conflict diagnostics

instead of only a generic “generation failed”

## Minimal Endpoint Summary

### JSON generation

- `POST /api/v1/memoriais/eletrico`
- `POST /api/v1/memoriais/telecom`
- `POST /api/v1/memoriais/gas-natural`
- `POST /api/v1/memoriais/glp`

### Upload only

- `POST /api/v1/memoriais/eletrico/upload`
- `POST /api/v1/memoriais/telecom/upload`
- `POST /api/v1/memoriais/gas-natural/upload`
- `POST /api/v1/memoriais/glp/upload`

### Generate from files

- `POST /api/v1/memoriais/eletrico/from-files`
- `POST /api/v1/memoriais/telecom/from-files`
- `POST /api/v1/memoriais/gas-natural/from-files`
- `POST /api/v1/memoriais/glp/from-files`

### Electric review session

- `POST /api/v1/memoriais/eletrico/sessoes`
- `GET /api/v1/memoriais/eletrico/sessoes/{session_id}`
- `PATCH /api/v1/memoriais/eletrico/sessoes/{session_id}/contexto`
- `POST /api/v1/memoriais/eletrico/sessoes/{session_id}/gerar`

## Recommendation For Frontend Delivery

If the frontend team is implementing fast, the most useful order is:

1. electric/telecom/gas/glp direct JSON generation
2. generic from-files uploader/download flow
3. electric review session flow
4. advanced extraction-report/conflict UI

This sequence matches backend maturity and keeps the first interface simpler.
