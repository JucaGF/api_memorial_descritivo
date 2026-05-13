# GLP v2 e robustez de backend — log de progresso (2026-05-13)

## Objetivo

Implementar o plano **GLP v2 backend robustness**: contrato GLP v2 versionado, persistência de `final_context` / relatórios / conflitos, envelope de erro com `error.request_id`, limites de upload (incluindo páginas PDF), resiliência do cliente OpenAI, normalizador de diâmetros, `tem_gerador` no memorial elétrico, e rotas GLP v2 protegidas por feature flag e pelo DOCX humano.

## Resultado

- **M1**: Migração `004_generated_memorials_context.sql`, store e GET com `include_context=true` (já integrados antes desta sessão).
- **M2**: Respostas de validação e cliente via `build_*_error_response` com `error.request_id` mantendo `detail` / `errors`.
- **M3**: `UploadTooManyPagesError` (`upload_too_many_pages`), contagem com PyMuPDF após gravar cada PDF; 413 em conjunto com os demais limites.
- **M4**: Timeout configurável em `OpenAI()`; `_extract_batch` registra falhas por arquivo com `BatchFileExtractionResult(extraction_type="error", error=...)`.
- **M5**: `diameter_normalizer` + testes (já presentes).
- **M6**: `load_glp_v2_schema` / `validate_memorial_glp_v2_context` + testes em `test_memorial_validator.py`.
- **M7**: Modelos Pydantic v2, `GLP_V2_EXTRACTION_PROMPT` / merge, `extract_glp_v2_with_llm_result`.
- **M8**: `map_extraction_to_partial_glp_v2_context`, diâmetros, guard fogão/apartamentos → `_glp_v2_critical_conflicts`.
- **M9**: `_assemble_glp_v2_payload`, `generate_memorial_glp_v2_from_ingested_files`, fixture `glp_v2_makai_expected.json` (forma agnóstica de nome de projeto).
- **M10**: `POST /api/v1/memoriais/glp/v2/from-files` e `/from-files/persist`, `GLP_V2_ENABLED`, 503 `glp_v2_template_pending` sem `template.docx`.
- **M11**: `gerador.tem_gerador` opcional no schema elétrico, derivação no `context_builder`, `_extract_tem_gerador` + testes; `tipo_atendimento` pode ser `null` com gerador presente.
- **Persistência**: tipo `glp_v2` / `memorial_glp_v2.docx` no storage.

## Pendências (fora do escopo deste repo)

- Autoria manual de `templates/glp/v2/template.docx` no Word (binário).
- Frontend `dashboard-memorial` (repo externo).
- Aplicar migração 004 no Supabase em produção.

## Verificação

Testes direcionados executados com sucesso (validator GLP v2, mapper v2, resiliência de batch, limites de upload incluindo páginas PDF, rotas GLP v2, assembly + fixture MAKAI).

`python -m unittest discover -s tests` na pasta `api_memorial_descritivo` pode ainda reportar falhas **pré-existentes do ambiente Windows / OneDrive**:

- `PackageNotFoundError` ao renderizar memoriais quando `template.docx` é placeholder do OneDrive (download real do binário necessário).
- `PermissionError` em `test_generated_memorial_store` com `NamedTemporaryFile` no Windows.

