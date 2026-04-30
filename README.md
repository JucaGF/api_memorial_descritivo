# API Memorial Descritivo

Sistema para geração automática de memoriais descritivos de engenharia a partir de arquivos técnicos, com foco operacional no **memorial elétrico v1** e no **memorial telecom v1**.

O projeto recebe arquivos de projeto, extrai informações relevantes, monta um contexto estruturado, valida esse contexto contra o contrato do template e gera automaticamente um memorial em **DOCX**. O sistema também já possui um fluxo de **revisão manual por sessão**, permitindo corrigir o contexto antes da geração final.

---

# Objetivo do projeto

Automatizar a criação de memoriais descritivos utilizados em projetos de engenharia, reduzindo trabalho manual, aumentando consistência e mantendo a geração final alinhada a templates documentais reais.

Fluxo conceitual do sistema:

1. Recebimento de arquivos técnicos
2. Extração de informações relevantes
3. Conversão para contexto estruturado do memorial
4. Validação do contexto contra o schema do template
5. Geração do DOCX final
6. Revisão humana opcional antes da geração final

---

# Escopo atual

O escopo atual está dividido em duas frentes implementadas e uma próxima frente planejada:

- **memorial elétrico v1**: fluxo funcional de ponta a ponta (JSON, arquivos e revisão por sessão)
- **memorial telecom v1**: fluxo funcional de geração por JSON e por arquivos
- **memorial gás**: próxima expansão planejada, com dois casos distintos
  - **gás GLP**
  - **gás natural**

O sistema já possui:

- template DOCX versionado
- schema JSON do contrato de dados
- pipeline de geração por JSON
- pipeline de ingestão por arquivos
- pipeline de geração direta a partir de arquivos
- fluxo de revisão manual por sessão
- persistência de sessão em filesystem
- persistência opcional de sessão em Supabase
- suíte de testes automatizados cobrindo serviços, stores, mapper e API

## Respostas de erro

Para production readiness, a API agora usa um tratamento global mínimo para erros de framework e falhas internas inesperadas.

- Todas as respostas passam a devolver `X-Request-ID`.
- Erros internos inesperados retornam `500` com mensagem genérica, sem stack trace nem mensagem bruta da exceção.
- Erros de validação do FastAPI retornam `422` com `detail` legível e um envelope `error`.
- `HTTPException` e rotas inexistentes preservam o status code e retornam um envelope previsível.

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

Para validação, `error.details` contém os itens detalhados e `detail` continua trazendo a lista de erros para compatibilidade.

Além disso, o próximo eixo de evolução do projeto é a implementação do memorial de gás, separado desde o início entre os cenários de **GLP** e **gás natural**.

---

# Estado atual do projeto

O projeto já saiu da fase de prova de conceito e hoje possui uma base funcional de backend para geração de memoriais com duas trilhas ativas: elétrico e telecom.

## O que já está implementado

### 1. Template e contrato do memorial elétrico v1

Arquivos principais:

```text
templates/eletrico/v1/template.docx
templates/eletrico/v1/schema.json
templates/eletrico/v1/notes.md
```

O template usa **docxtpl** com sintaxe Jinja2 para renderização condicional.
O `schema.json` define o contrato esperado para o contexto.
O `notes.md` documenta decisões e observações do template.

### 2. Template e contrato do memorial telecom v1

Arquivos principais:

```text
templates/telecom/v1/template.docx
templates/telecom/v1/schema.json
templates/telecom/v1/notes.md
```

O template de telecom usa **docxtpl** com placeholders Jinja2.
O `schema.json` define o contrato esperado para o contexto.
O `notes.md` documenta decisões e observações do template.

### 3. Geração por JSON

O sistema já aceita um contexto estruturado pronto e gera o memorial DOCX a partir dele.

Esse fluxo é útil quando os dados do memorial já estão disponíveis e validados fora da etapa de extração.

### 4. Ingestão e geração por arquivos

O backend já possui fluxo para:

- receber arquivos de projeto
- ingerir esses arquivos temporariamente
- extrair conteúdo relevante
- mapear a extração para contexto parcial do memorial
- avaliar cobertura da extração
- gerar o documento final

### 5. Revisão manual por sessão

O sistema já implementa um fluxo de revisão intermediária antes da geração final.

Esse fluxo permite:

- criar uma sessão de revisão
- disparar extração em background
- persistir contexto parcial
- persistir relatório de extração
- aplicar correções manuais
- fazer merge das correções com o contexto parcial
- gerar o memorial final a partir do contexto revisado

### 6. Session store

O armazenamento de sessões hoje possui duas possibilidades:

- backend em filesystem
- backend opcional em Supabase, habilitado por variáveis de ambiente

A sessão contém informações como:

- status do processamento
- contexto parcial
- relatório de extração
- correções aplicadas
- metadados de expiração

### 7. Mapper semântico de extração

O projeto já possui um `extraction_mapper` com múltiplas fases de evolução, cobrindo extração por proximidade, leitura de campos rotulados, preenchimento de campos derivados e evidências por campo.

Isso permite transformar a saída de extração em um contexto mais próximo do contrato real do template.

### 8. Testes automatizados

A suíte de testes já vai além da renderização do template e cobre diferentes partes do backend, incluindo:

- renderização do memorial
- extraction mapper
- session store
- Supabase session store
- contratos da API
- fluxo de sessão
- pipeline de geração

## Storage dos memoriais persistidos

Os memoriais criados pelo endpoint `POST /api/v1/memoriais/{memorial_type}/from-files/persist` usam dois componentes distintos:

1. metadata em `generated_memorials`
2. arquivo DOCX em Supabase Storage

O DOCX pode ser gerado temporariamente em filesystem local durante a renderização, mas esse arquivo é apenas transitório e é removido após o upload. A persistência real do artefato depende do bucket configurado.

### Configuração recomendada

- `GENERATED_MEMORIALS_BUCKET`: bucket privado onde os DOCX persistidos serão gravados
- `GENERATED_MEMORIALS_SIGNED_URL_TTL`: tempo de vida da URL assinada de download
- `SUPABASE_URL` e `SUPABASE_KEY`: credenciais usadas para metadata e storage

### Regra de produção

Em `APP_ENV=production`, o backend exige configuração explícita de:

- `GENERATED_MEMORIALS_BUCKET`
- `SUPABASE_URL`
- `SUPABASE_KEY`

Isso evita depender silenciosamente de defaults implícitos ou de storage efêmero para artefatos que precisam continuar disponíveis no histórico do dashboard.

### Contrato de download e exclusão

- O download consulta a metadata pelo `memorial_id` e valida `storage_bucket` e `storage_path` antes de gerar a URL assinada.
- Se a metadata não existir, a API retorna `404`.
- Se a metadata existir mas o `status` ainda não for `ready`, a API retorna `409` com erro previsível e não tenta servir o artefato.
- Se o arquivo registrado não estiver mais disponível, a API retorna erro seguro sem expor path interno bruto.
- A exclusão remove primeiro o objeto no storage e só depois remove a metadata, evitando que o histórico aponte para um artefato que falhou ao ser apagado.

### Ciclo de estados dos memoriais persistidos

O endpoint `POST /api/v1/memoriais/{memorial_type}/from-files/persist` usa um ciclo mínimo e compatível com o dashboard:

1. cria a metadata com `status=processing`
2. faz upload do DOCX final para o bucket configurado
3. atualiza a metadata para `status=ready` somente após upload concluído
4. se o upload ou a persistência falharem, tenta marcar a metadata como `status=failed`

Com isso:

- o histórico não precisa tratar uma falha como memorial concluído;
- o download só é permitido para memoriais `ready`;
- falhas de storage retornam erro seguro e previsível para a API.

---

# Fluxos disponíveis hoje

Os fluxos abaixo já existem no backend. Parte deles está disponível hoje apenas para o memorial elétrico, enquanto JSON e geração por arquivos já existem também para telecom.

## 1. Geração direta por JSON

Usado quando o contexto do memorial já está pronto.

Fluxo:

1. A API recebe um JSON no formato esperado pelo schema
2. O contexto é validado
3. O template DOCX é renderizado
4. O memorial final é retornado

Status atual:

- **elétrico v1**: implementado
- **telecom v1**: implementado

## 2. Upload e ingestão de arquivos

Usado quando a intenção é apenas ingerir e preparar os arquivos para etapas posteriores do pipeline.

Fluxo:

1. A API recebe PDFs e/ou DOCX
2. Os arquivos são armazenados temporariamente
3. O backend executa a etapa de ingestão
4. O resultado fica disponível para o pipeline seguinte

Status atual:

- **elétrico v1**: implementado
- **telecom v1**: implementado

## 3. Geração a partir de arquivos

Usado quando se deseja que o sistema tente produzir o memorial diretamente com base nos arquivos enviados.

Fluxo:

1. A API recebe os arquivos
2. O backend ingere os arquivos
3. O conteúdo é extraído
4. A extração é convertida em contexto parcial
5. O contexto é validado
6. O memorial DOCX é gerado

Status atual:

- **elétrico v1**: implementado
- **telecom v1**: implementado

## 4. Revisão manual por sessão

Usado quando se deseja revisar ou corrigir o contexto antes da geração final.

Fluxo:

1. Criação da sessão
2. Extração em background
3. Persistência do contexto parcial e do relatório
4. Consulta da sessão
5. Correção manual do contexto
6. Geração final do memorial revisado

Esse fluxo é importante porque permite manter a geração final determinística, sem depender de uma extração perfeita em todos os campos.

Status atual:

- **elétrico v1**: implementado
- **telecom v1**: ainda não implementado

---

# Estrutura atual do repositório

A estrutura real do projeto hoje já é de um backend funcional, e não apenas de um conjunto de templates.

Estrutura principal:

```text
app/
  api/
  schemas/
  services/

templates/
  eletrico/
    v1/
  telecom/
    v1/

tests/
  fixtures/

scripts/

migrations/

AGENTS.md
README.md
requirements.txt
```

## Papel das principais pastas

### `app/api/`

Contém as rotas HTTP da aplicação e a orquestração dos fluxos expostos pela API.

### `app/schemas/`

Contém os schemas e modelos de entrada e saída usados pela API e pelos fluxos internos.

### `app/services/`

Contém a lógica de negócio do sistema, incluindo:

- pipeline de geração por JSON
- pipeline de geração por arquivos
- ingestão de arquivos
- extração e mapeamento
- context builder
- session store
- integração opcional com Supabase

### `templates/`

Contém os templates DOCX, schemas JSON e anotações de suporte para cada tipo e versão de memorial.
No estado atual:

- `eletrico/v1` possui template DOCX + schema + notas
- `telecom/v1` possui template DOCX + schema + notas

### `tests/`

Contém a suíte de testes automatizados, incluindo fixtures e arquivos de saída usados em validações.

### `scripts/`

Contém scripts auxiliares, incluindo testes específicos de renderização do template.

### `migrations/`

Contém migrations relacionadas à persistência, como a estrutura de sessões de revisão no Supabase.

---

# Componentes principais

## Rotas da API

As rotas atuais cobrem os principais fluxos do sistema:

- geração por JSON
- ingestão de arquivos
- geração por arquivos
- sessões de revisão
- atualização de contexto de sessão
- geração final a partir da sessão

No estágio atual:

- há rotas de JSON, upload e `from-files` para **elétrico**
- há rotas de JSON, upload e `from-files` para **telecom**
- o fluxo de **sessão de revisão** continua disponível apenas para **elétrico**

## Pipeline JSON

Responsável por:

- receber contexto já estruturado
- validar contra o schema
- renderizar o template DOCX

## Pipeline por arquivos

Responsável por:

- receber os arquivos ingeridos
- extrair conteúdo do projeto
- mapear extração para contexto parcial
- avaliar cobertura da extração
- gerar o memorial final

No estado atual, esse pipeline possui dois comportamentos relevantes:

- **elétrico v1**: mapper determinístico com suporte opcional a extração assistida por LLM
- **telecom v1**: mapper telecom dedicado com suporte opcional a extração assistida por LLM

## Extraction Mapper

Responsável por transformar a saída da extração em um contexto mais próximo do contrato do template.
Inclui lógica por campo, evidências e tratamento de diferentes padrões documentais.

Atualmente já existem regras específicas para:

- campos do memorial elétrico v1
- campos base do memorial telecom v1, incluindo correções derivadas de projetos reais usados em testes end-to-end

## Context Builder

Responsável por mesclar contexto parcial com correções humanas, preservando a lógica do fluxo de revisão.

## Session Store

Responsável por persistir sessões de revisão, estado do processamento, correções e relatórios.

## Supabase Session Store

Implementação opcional de persistência de sessão em Supabase, usada quando habilitada por configuração de ambiente.

---

# Regras importantes do sistema

- Para fluxos com template ativo (como elétrico v1 e telecom v1), o **template DOCX é a fonte de verdade do memorial**.
- O **schema JSON define o contrato de dados necessário para renderização**.
- A renderização final deve ser **determinística**.
- A geração final do memorial **não pode depender de LLM**.
- A extração dos dados pode evoluir com heurísticas, OCR, visão computacional ou LLM, mas o documento final deve continuar obedecendo ao template e ao schema.
- O fluxo de revisão manual existe para compensar limitações naturais da extração automática.

---

# Tecnologias utilizadas

- Python
- FastAPI
- docxtpl
- python-docx
- jsonschema
- OpenAI API
- Supabase
- unittest
- ruff
- uv / `.venv`

Dependendo da evolução do projeto, outras bibliotecas auxiliares podem existir no `requirements.txt`.

---

# Execução local

## Instalação de dependências

```bash
uv venv
UV_CACHE_DIR=/tmp/uv-cache uv pip install --python .venv/bin/python -r requirements.txt
```

## Rodando a API

Caso o entrypoint da aplicação seja `app.main:app`, use:

```bash
.venv/bin/uvicorn app.main:app --reload
```

Se o projeto estiver usando outro entrypoint, ajuste o comando conforme a estrutura real do backend.

---

# Testes

## Teste específico de renderização do template

```bash
.venv/bin/python scripts/test_render_eletrico.py
```

Arquivos gerados por esse script são salvos em:

```text
tests/output/
```

## Rodar toda a suíte de testes

```bash
.venv/bin/python -m unittest discover -s tests
```

## Rodar arquivos específicos de teste

Exemplo:

```bash
.venv/bin/python -m unittest tests.test_session_store tests.test_supabase_session_store tests.test_api
```

Exemplo de testes direcionados para os memoriais atuais:

```bash
.venv/bin/python -m unittest tests.test_pipeline tests.test_pipeline_from_files tests.test_api
```

---

# Persistência de sessão

O sistema suporta dois modos principais de persistência para sessões de revisão:

## Filesystem

Modo padrão e simples para desenvolvimento local.
As sessões são armazenadas em arquivos locais.

## Supabase

Modo opcional habilitado por variáveis de ambiente.
Nesse modo, a persistência das sessões passa a ser feita em tabela própria, com migration dedicada.

---

# Limitações atuais

Apesar do backend já estar funcional, ainda existem pontos em evolução:

- o fluxo de revisão por sessão ainda pode ganhar contratos mais tipados
- a cobertura de testes end-to-end completos ainda pode ser ampliada
- há campos que ainda permanecem pendentes ou dependentes de heurísticas no mapper
- a robustez operacional do fluxo por arquivos ainda está sendo refinada
- a estratégia de cleanup e lifecycle de arquivos temporários ainda pode evoluir
- a integração com Supabase ainda pode ser fortalecida para cenários mais concorrentes
- o memorial telecom v1 já está funcional, mas ainda pode ganhar extração mais robusta e fluxo de revisão por sessão
- o memorial de gás ainda não foi iniciado no backend

---

# Próximos passos

Os próximos passos do projeto estão concentrados em robustez, previsibilidade e expansão gradual da cobertura do pipeline.

Prioridades atuais:

1. reforçar o ciclo de vida e cleanup dos arquivos temporários
2. tipar melhor os contratos do fluxo de revisão
3. reduzir duplicação interna no pipeline por arquivos
4. ampliar testes end-to-end do fluxo de sessão
5. fortalecer a integração e consistência do session store com Supabase
6. evoluir a cobertura do extraction mapper e da extração assistida por LLM para os campos ainda pendentes
7. implementar o **memorial de gás** como próxima frente funcional
8. separar a implementação de gás em dois casos explícitos desde o início:
   - **gás GLP**
   - **gás natural**
9. preservar a mesma disciplina já aplicada em elétrico e telecom:
   - template DOCX como fonte de verdade
   - schema JSON como contrato
   - renderização final determinística

---

# Observações finais

Este README descreve o estado atual do projeto com foco principal nos memoriais **elétrico v1** e **telecom v1**, já integrados ao backend em diferentes níveis de maturidade operacional.

O sistema já possui uma base funcional de geração automática com revisão manual opcional no fluxo elétrico, geração por arquivos em elétrico e telecom, e segue em evolução para ganhar mais robustez operacional, melhor tipagem de contratos, maior cobertura de testes e expansão para novos tipos de memorial.

A próxima etapa planejada é a implementação do **memorial de gás**, tratado desde o início em dois cenários independentes:

- **gás GLP**
- **gás natural**
