# API Memorial Descritivo

Backend para geração automática de memoriais descritivos de engenharia a partir de contexto estruturado ou arquivos técnicos. O foco operacional atual é a geração determinística de documentos DOCX a partir de contratos de template e schema, com suporte a revisão manual por sessão e persistência de memoriais gerados.

Este `README` é voltado principalmente para quem vai integrar a API, mas também inclui o necessário para rodar, configurar, testar e manter o projeto localmente.

## Visão geral

A API recebe dados estruturados ou arquivos de projeto, executa extração e mapeamento para o contrato do memorial, valida o resultado contra o schema correspondente e gera um DOCX final.

Fluxos principais já suportados:

- geração direta por JSON
- ingestão de arquivos
- geração direta a partir de arquivos
- revisão manual por sessão
- persistência de memoriais gerados com metadata e download assinado

Princípios que governam o sistema:

- o template DOCX é a fonte de verdade da estrutura final do documento
- o schema JSON é o contrato de dados para renderização
- a geração final precisa permanecer determinística
- saída de LLM pode ajudar na extração, mas não pode ser usada como conteúdo final do memorial
- todo contexto deve ser validado antes da renderização

## Estado atual

O projeto já está além de um protótipo. Hoje ele possui uma base funcional de backend com trilhas ativas para múltiplos tipos de memorial.

Tipos de memorial atualmente suportados pela API:

- `eletrico`
- `telecom`
- `gas-natural`
- `glp`

Observações sobre o estado do produto:

- `memorial eletrico v1` é a trilha mais madura, incluindo fluxo completo de revisão por sessão.
- `memorial telecom v1` possui geração por JSON e por arquivos.
- `memorial gas natural v1` possui template, schema e fluxo de geração.
- `memorial glp` possui trilhas `v1` e `v2` no repositório; a API pública principal usa `glp`, enquanto o histórico persistido também aceita filtro por `glp_v2`.

## Como a API funciona

### 1. Geração por JSON

Use esse fluxo quando o contexto do memorial já estiver estruturado fora da etapa de extração.

Fluxo esperado:

1. receber payload JSON
2. validar contra o schema do memorial
3. renderizar o DOCX
4. retornar o arquivo gerado

### 2. Ingestão de arquivos

Use esse fluxo quando o frontend ou outro cliente precisar apenas enviar arquivos e deixar o backend prepará-los para extração posterior.

### 3. Geração a partir de arquivos

Use esse fluxo quando os PDFs do projeto forem a entrada principal.

Fluxo esperado:

1. receber upload dos arquivos
2. ingerir temporariamente
3. extrair dados relevantes
4. mapear para o contexto do memorial
5. validar o contexto
6. renderizar o DOCX

### 4. Revisão por sessão

Esse é o fluxo mais importante para casos em que a extração automática precisa de confirmação humana antes da geração final.

Fluxo esperado:

1. criar uma sessão
2. disparar a extração em background
3. persistir contexto parcial e relatório de extração
4. permitir correções manuais
5. mesclar correções com o contexto
6. gerar o memorial final a partir do contexto revisado

Hoje esse fluxo está exposto principalmente para `eletrico`.

### 5. Persistência de memoriais gerados

Além dos endpoints binários que retornam o DOCX diretamente, a API também permite gerar o memorial, salvar o artefato em storage e persistir metadata para listagem, consulta e download posterior.

## Integração

### Base path

Todas as rotas públicas ficam sob:

```text
/api/v1
```

### Tipos de resposta

A API retorna três categorias principais:

- JSON de sucesso
- JSON de erro
- arquivo DOCX

Quando a geração é bem-sucedida via endpoints binários, a resposta usa:

```text
application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

O cliente deve tratar essa resposta como download binário.

### Header de rastreio

Todas as respostas incluem:

```text
X-Request-ID
```

Se o cliente enviar esse header, a API o preserva. Caso contrário, um ID é gerado no backend.

Isso é útil para:

- correlação de logs
- troubleshooting entre frontend e backend
- rastreio de erros em produção

### Famílias de rotas

Na prática, a integração fica mais simples se você pensar em cinco grupos:

1. healthcheck
2. geração por JSON
3. ingestão e geração por arquivos
4. revisão por sessão
5. memoriais persistidos

## Healthcheck

Rotas disponíveis:

- `GET /health`
- `GET /health/live`
- `GET /health/ready`

Comportamento esperado:

- `/health` retorna um status simples
- `/health/live` confirma que a aplicação está viva
- `/health/ready` valida prontidão operacional e pode retornar `503` se algum check crítico falhar

## Memorials por JSON

Esses endpoints recebem um payload JSON já estruturado e retornam o DOCX diretamente.

Rotas:

- `POST /api/v1/memoriais/eletrico`
- `POST /api/v1/memoriais/telecom`
- `POST /api/v1/memoriais/gas-natural`
- `POST /api/v1/memoriais/glp`

Uso recomendado:

- sistemas que já possuem os dados do memorial em formato estruturado
- integrações em que a etapa de extração acontece fora desta API

Resultado de sucesso:

- status `200`
- corpo binário DOCX

## Ingestão e geração por arquivos

### Geração binária direta

Esses endpoints recebem `multipart/form-data` com arquivos e devolvem o DOCX na própria resposta.

Rotas:

- `POST /api/v1/memoriais/eletrico/from-files`
- `POST /api/v1/memoriais/telecom/from-files`
- `POST /api/v1/memoriais/gas-natural/from-files`
- `POST /api/v1/memoriais/glp/from-files`

Payload esperado:

- campo repetido `files`
- arquivos de projeto, tipicamente PDFs

Resultado de sucesso:

- status `200`
- corpo binário DOCX

### Geração com persistência

Esses endpoints geram o memorial, enviam o DOCX para storage e retornam metadata em JSON.

Rotas:

- `POST /api/v1/memoriais/eletrico/from-files/persist`
- `POST /api/v1/memoriais/telecom/from-files/persist`
- `POST /api/v1/memoriais/gas-natural/from-files/persist`
- `POST /api/v1/memoriais/glp/from-files/persist`

Payload esperado:

- `multipart/form-data`
- campo repetido `files`
- campo opcional `observations`

Exemplo com JavaScript:

```ts
const form = new FormData();
files.forEach((file) => form.append("files", file));
form.append("observations", "Observações opcionais do usuário");

const response = await fetch("/api/v1/memoriais/telecom/from-files/persist", {
  method: "POST",
  body: form,
});

const body = await response.json();
```

Exemplo de resposta:

```json
{
  "id": "uuid",
  "type": "telecom",
  "project_name": "Memorial Telecom",
  "status": "ready",
  "observations": "Observações opcionais do usuário",
  "pdf_filenames": ["projeto.pdf"],
  "created_at": "2026-04-17T12:00:00Z",
  "updated_at": "2026-04-17T12:00:00Z",
  "download_url": "https://signed-url"
}
```

## Memoriais persistidos

Esses endpoints são úteis para dashboard, histórico e download posterior.

### Listagem

- `GET /api/v1/memoriais`
- `GET /api/v1/memoriais?type=telecom`

Filtros suportados atualmente:

- `eletrico`
- `telecom`
- `gas-natural`
- `glp`
- `glp_v2`

Resposta:

```json
{
  "memorials": []
}
```

### Detalhe

Use:

```text
GET /api/v1/memoriais/{memorial_id}
```

Parâmetro opcional:

- `include_context=true` para retornar também o contexto persistido, quando aplicável

### Download

Use:

```text
GET /api/v1/memoriais/{memorial_id}/download
```

Esse endpoint retorna uma URL assinada. Se a URL anterior expirar, chame o endpoint novamente.

### Exclusão

Use:

```text
DELETE /api/v1/memoriais/{memorial_id}
```

Comportamento:

- remove o objeto do storage
- remove a metadata persistida
- retorna `204` em caso de sucesso

## Sessões de revisão

O backend possui fluxo de revisão manual com persistência de sessão. Esse fluxo é crítico para `eletrico` e deve ser tratado como parte sensível do contrato do sistema.

Fluxo esperado para integradores:

1. criar sessão
2. acompanhar o processamento
3. ler contexto parcial e relatório de extração
4. enviar correções manuais
5. solicitar geração final após revisão

Como o contrato dessa trilha é mais específico e pode evoluir com mais cuidado do que os endpoints binários, consulte também:

- [docs/frontend-api-reference.md](/home/juca/Projects/api_memorial_descritivo/docs/frontend-api-reference.md)

## Modelo de erro

### Erros estruturados

A API usa envelopes de erro previsíveis para validação, erros HTTP e falhas internas.

Formato base:

```json
{
  "detail": "Mensagem legada/compatível",
  "error": {
    "code": "internal_server_error",
    "message": "Erro interno ao processar a requisição.",
    "request_id": "..."
  }
}
```

### Erro de validação de memorial

Quando o payload ou o contexto extraído não atende ao schema, a API normalmente retorna `400` com lista de problemas.

Exemplo:

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

Em alguns fluxos, também pode existir `extraction_report`.

### Conflito quantitativo não resolvido

Quando a extração encontra valores quantitativos divergentes e a API bloqueia a geração para evitar memorial incorreto, o retorno é `409`.

Exemplo:

```json
{
  "detail": "Encontramos valores diferentes nos quantitativos do projeto. A geração foi bloqueada para evitar um memorial incorreto.",
  "errors": [
    {
      "path": "$.pontos_utilizacao.conflitos",
      "message": "Conflitos criticos GLP v2 sem resolucao.",
      "validator": "glp_v2_conflict"
    }
  ],
  "conflicts": [
    {
      "tipo": "glp_v2_points_total_mismatch",
      "status": "unresolved"
    }
  ],
  "error": {
    "code": "quantitative_conflict_unresolved",
    "message": "Encontramos valores diferentes nos quantitativos do projeto. A geração foi bloqueada para evitar um memorial incorreto."
  }
}
```

### Erros de validação do FastAPI

Payloads inválidos na própria requisição HTTP retornam `422`.

### Erros internos

Falhas inesperadas retornam `500` com mensagem segura, sem stack trace e sem vazamento de exceções brutas.

### Recomendações para o cliente

- sempre leia `detail`
- se existir `error`, use `error.code` para tratamento programático
- se existir `errors`, apresente a lista em UI de validação
- se existir `extraction_report`, trate como apoio para depuração ou revisão humana
- use `X-Request-ID` ao reportar falhas

## Limites de upload

O backend possui limites configuráveis para evitar falhas opacas em parsing, OCR, extração e renderização.

Variáveis atualmente suportadas:

- `MAX_FILE_COUNT`
- `MAX_FILE_SIZE_MB`
- `MAX_TOTAL_UPLOAD_MB`
- `MAX_PDF_PAGES`

Defaults:

- `10` arquivos
- `50 MB` por arquivo
- `200 MB` no total
- `100` páginas por PDF

Violações desses limites retornam erro de cliente, em geral `413` para excesso de tamanho/quantidade.

## Rodando localmente

### Requisitos

- Python 3.11+ recomendado
- ambiente virtual Python
- dependências de `requirements.txt`

### Setup

Crie e ative um ambiente virtual:

```bash
python -m venv .venv
source .venv/bin/activate
```

Instale as dependências:

```bash
pip install -r requirements.txt
```

### Executando a API

Com o ambiente ativo:

```bash
uvicorn app.main:app --reload
```

Por padrão, a aplicação ficará acessível em:

```text
http://127.0.0.1:8000
```

### Variáveis de ambiente

Configuração mínima comum para ambiente local:

```env
APP_ENV=local
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Variáveis suportadas pela aplicação:

- `APP_ENV`
- `CORS_ALLOWED_ORIGINS`
- `CORS_ORIGINS`
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY` ou `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_KEY` (legado)
- `GENERATED_MEMORIALS_BUCKET`
- `GENERATED_MEMORIALS_SIGNED_URL_TTL`
- `MAX_FILE_COUNT`
- `MAX_FILE_SIZE_MB`
- `MAX_TOTAL_UPLOAD_MB`
- `MAX_PDF_PAGES`
- `OPENAI_API_KEY`

Comportamento por ambiente:

- em `local` e `test`, a API aceita origins locais padrão se CORS não for informado
- em `production`, `CORS_ALLOWED_ORIGINS` é obrigatório
- em `production`, a persistência de memoriais exige `GENERATED_MEMORIALS_BUCKET`, `SUPABASE_URL` e `SUPABASE_SECRET_KEY` ou `SUPABASE_SERVICE_ROLE_KEY`

## Supabase e persistência

O projeto suporta persistência de sessões e de memoriais gerados com Supabase.

### Memoriais persistidos

Os endpoints `from-files/persist` usam dois componentes:

1. metadata em banco
2. arquivo DOCX em Supabase Storage

Configuração recomendada:

```env
SUPABASE_URL=...
SUPABASE_SECRET_KEY=...
GENERATED_MEMORIALS_BUCKET=generated-memorials
GENERATED_MEMORIALS_SIGNED_URL_TTL=3600
```

Migrations relacionadas:

- `migrations/002_generated_memorials.sql`
- `migrations/003_create_storage_bucket.sql`
- `migrations/004_generated_memorials_context.sql`
- `migrations/005_auth_profiles_and_ownership.sql`

### Auth e usuários

O dashboard usa Supabase Auth com email/senha. Cadastro público deve ficar desabilitado no Supabase; usuários novos são criados apenas pela API em `/api/v1/admin/users`, acessível por perfis `owner`.

Setup inicial:

1. Crie o primeiro usuário em Supabase Authentication.
2. Execute `migrations/005_auth_profiles_and_ownership.sql`.
3. Confirme que o usuário `adc8635c-193a-4568-9896-2bc523bba923` foi inserido em `public.user_profiles` como `owner` durante o desenvolvimento.
4. Antes da produção, crie/promova o usuário do engenheiro chefe para `owner` e demova ou desative o usuário temporário.

Comportamento do ciclo de estados:

1. cria metadata com `status=processing`
2. faz upload do DOCX final
3. muda metadata para `status=ready`
4. em falha, tenta marcar como `status=failed`

Regras importantes:

- download só é permitido para memoriais com `status=ready`
- ausência de metadata retorna `404`
- artefato ausente no storage retorna erro seguro
- indisponibilidade de storage retorna `503`

### Sessões de revisão

O backend também possui store em filesystem e store opcional em Supabase para sessões de revisão. Mudanças nessa área precisam preservar alinhamento entre os dois backends.

Migration relacionada:

- `migrations/001_review_sessions.sql`

## Estrutura do projeto

Mapa dos diretórios mais importantes:

```text
app/
  api/         rotas HTTP e tratamento de erros
  schemas/     contratos de request/response e modelos internos
  services/    ingestão, extração, mapeamento, sessão, validação e renderização

templates/
  eletrico/v1/
  telecom/v1/
  gas_natural/v1/
  glp/v1/
  glp/v2/

tests/         cobertura unitária e de integração
migrations/    SQL de suporte a Supabase/Postgres/Storage
docs/          referência de integração, planos e notas operacionais
projects/      exemplos de arquivos técnicos usados em desenvolvimento
```

Arquivos especialmente úteis:

- [AGENTS.md](/home/juca/Projects/api_memorial_descritivo/AGENTS.md)
- [docs/PLANS.md](/home/juca/Projects/api_memorial_descritivo/docs/PLANS.md)
- [docs/frontend-api-reference.md](/home/juca/Projects/api_memorial_descritivo/docs/frontend-api-reference.md)
- [docs/frontend-persistent-memorials.md](/home/juca/Projects/api_memorial_descritivo/docs/frontend-persistent-memorials.md)

## Templates e schemas

Cada memorial depende da coerência entre:

- `template.docx`
- `schema.json`
- `notes.md`

Exemplos:

```text
templates/eletrico/v1/template.docx
templates/eletrico/v1/schema.json
templates/eletrico/v1/notes.md
```

Restrições importantes:

- não alterar comportamento do template sem checar impacto no schema
- não alterar schema sem checar impacto no template e nos testes
- o DOCX final não pode conter placeholders Jinja não resolvidos
- a renderização deve continuar determinística e orientada por contrato

## Testes

O projeto usa `unittest` como fluxo principal de validação automatizada.

Comandos úteis:

```bash
python -m unittest discover -s tests
python -m unittest tests.test_api
python -m unittest tests.test_session_store
python -m unittest tests.test_supabase_session_store
python -m unittest tests.test_generated_memorial_api
python -m unittest tests.test_pipeline
python -m unittest tests.test_pipeline_from_files
python -m unittest tests.test_memorial_renderer
python -m unittest tests.test_memorial_validator
python -m unittest tests.test_extraction_mapper
```

Recomendação por tipo de mudança:

- mudanças de API: `tests.test_api`
- persistência de sessão: `tests.test_session_store` e `tests.test_supabase_session_store`
- memoriais persistidos: `tests.test_generated_memorial_api` e `tests.test_generated_memorial_store`
- extração e mapeamento: testes de pipeline, mapper e extractor
- renderização e validação: `tests.test_memorial_renderer` e `tests.test_memorial_validator`
- mudanças transversais: suíte completa

## Convenções e contratos que não devem quebrar

- preservar comportamento da API, salvo quando a mudança exigir alteração explícita
- validar dados antes de renderizar
- manter geração final determinística
- não usar LLM para gerar o conteúdo final do memorial
- preservar coerência entre filesystem e Supabase nos fluxos de sessão
- preferir mudanças pequenas e localizadas

## Referências adicionais

- [docs/frontend-api-reference.md](/home/juca/Projects/api_memorial_descritivo/docs/frontend-api-reference.md)
- [docs/frontend-persistent-memorials.md](/home/juca/Projects/api_memorial_descritivo/docs/frontend-persistent-memorials.md)
- [docs/railway-healthchecks.md](/home/juca/Projects/api_memorial_descritivo/docs/railway-healthchecks.md)

## Resumo rápido para integradores

Se você só precisa consumir a API:

1. escolha entre geração por JSON, por arquivos ou por persistência
2. trate sucesso como DOCX binário ou JSON, dependendo do endpoint
3. trate falhas pelo envelope `error` e pelo campo `detail`
4. preserve `X-Request-ID` nos logs do cliente
5. use os endpoints `/persist` para histórico e download assinado
