# Persistent Memorials Frontend Handoff

## Purpose

The API now exposes frontend-friendly endpoints for generating memorial DOCX files, saving the generated document in Supabase Storage, and persisting metadata in Supabase Postgres.

Use these endpoints from the dashboard instead of keeping generated memorial history only in local React state.

## Supabase Requirements

Run this migration in Supabase:

```text
migrations/002_generated_memorials.sql
```

Create a private Storage bucket:

```text
generated-memorials
```

Required backend environment:

```env
SUPABASE_URL=...
SUPABASE_KEY=...
GENERATED_MEMORIALS_BUCKET=generated-memorials
GENERATED_MEMORIALS_SIGNED_URL_TTL=3600
```

## Type Mapping

The dashboard currently uses frontend type ids. Map them to API slugs:

```ts
telecomunicacoes -> telecom
eletrico -> eletrico
gas_natural -> gas-natural
gas_glp -> glp
```

## Generate and Persist From Files

Use:

```text
POST /api/v1/memoriais/{tipo}/from-files/persist
```

Where `{tipo}` is one of:

```text
eletrico
telecom
gas-natural
glp
```

Request:

- `multipart/form-data`
- repeated `files`
- optional `observations`

Example:

```ts
const form = new FormData();
files.forEach((file) => form.append("files", file));
form.append("observations", observations);

const response = await axios.post(
  `${baseUrl}/api/v1/memoriais/telecom/from-files/persist`,
  form
);
```

Success response:

```json
{
  "id": "uuid",
  "type": "telecom",
  "project_name": "Memorial Telecom",
  "status": "ready",
  "observations": "texto opcional",
  "pdf_filenames": ["projeto.pdf"],
  "created_at": "2026-04-17T12:00:00Z",
  "updated_at": "2026-04-17T12:00:00Z",
  "download_url": "https://signed-url"
}
```

## List Memorials

Use:

```text
GET /api/v1/memoriais
GET /api/v1/memoriais?type=telecom
```

Response:

```json
{
  "memorials": []
}
```

## Detail and Download

Use:

```text
GET /api/v1/memoriais/{id}
GET /api/v1/memoriais/{id}/download
```

`download_url` is signed and expires. If a previously returned URL stops working, call `/download` again.

## Frontend Notes

- Convert backend snake_case fields to the current frontend camelCase model in one adapter function.
- Keep the older binary DOCX endpoints available only as fallback; the dashboard should prefer `/persist`.
- The correction/review-session flow remains out of scope for now.
