# API Memorial Descritivo

Sistema para geração automática de memoriais descritivos de engenharia a partir de arquivos técnicos, com foco atual no **memorial elétrico v1**.

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

O escopo implementado hoje está concentrado no **memorial elétrico v1**.

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

---

# Estado atual do projeto

O projeto já saiu da fase de prova de conceito de template e hoje possui uma primeira base funcional de backend para geração do memorial elétrico.

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

### 2. Geração por JSON

O sistema já aceita um contexto estruturado pronto e gera o memorial DOCX a partir dele.

Esse fluxo é útil quando os dados do memorial já estão disponíveis e validados fora da etapa de extração.

### 3. Ingestão e geração por arquivos

O backend já possui fluxo para:

- receber arquivos de projeto
- ingerir esses arquivos temporariamente
- extrair conteúdo relevante
- mapear a extração para contexto parcial do memorial
- avaliar cobertura da extração
- gerar o documento final

### 4. Revisão manual por sessão

O sistema já implementa um fluxo de revisão intermediária antes da geração final.

Esse fluxo permite:

- criar uma sessão de revisão
- disparar extração em background
- persistir contexto parcial
- persistir relatório de extração
- aplicar correções manuais
- fazer merge das correções com o contexto parcial
- gerar o memorial final a partir do contexto revisado

### 5. Session store

O armazenamento de sessões hoje possui duas possibilidades:

- backend em filesystem
- backend opcional em Supabase, habilitado por variáveis de ambiente

A sessão contém informações como:

- status do processamento
- contexto parcial
- relatório de extração
- correções aplicadas
- metadados de expiração

### 6. Mapper semântico de extração

O projeto já possui um `extraction_mapper` com múltiplas fases de evolução, cobrindo extração por proximidade, leitura de campos rotulados, preenchimento de campos derivados e evidências por campo.

Isso permite transformar a saída de extração em um contexto mais próximo do contrato real do template.

### 7. Testes automatizados

A suíte de testes já vai além da renderização do template e cobre diferentes partes do backend, incluindo:

- renderização do memorial
- extraction mapper
- session store
- Supabase session store
- contratos da API
- fluxo de sessão
- pipeline de geração

---

# Fluxos disponíveis hoje

## 1. Geração direta por JSON

Usado quando o contexto do memorial já está pronto.

Fluxo:

1. A API recebe um JSON no formato esperado pelo schema
2. O contexto é validado
3. O template DOCX é renderizado
4. O memorial final é retornado

## 2. Upload e ingestão de arquivos

Usado quando a intenção é apenas ingerir e preparar os arquivos para etapas posteriores do pipeline.

Fluxo:

1. A API recebe PDFs e/ou DOCX
2. Os arquivos são armazenados temporariamente
3. O backend executa a etapa de ingestão
4. O resultado fica disponível para o pipeline seguinte

## 3. Geração a partir de arquivos

Usado quando se deseja que o sistema tente produzir o memorial diretamente com base nos arquivos enviados.

Fluxo:

1. A API recebe os arquivos
2. O backend ingere os arquivos
3. O conteúdo é extraído
4. A extração é convertida em contexto parcial
5. O contexto é validado
6. O memorial DOCX é gerado

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

tests/
  fixtures/
  output/

scripts/

migrations/

.codex/
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

## Extraction Mapper

Responsável por transformar a saída da extração em um contexto mais próximo do contrato do template.
Inclui lógica por campo, evidências e tratamento de diferentes padrões documentais.

## Context Builder

Responsável por mesclar contexto parcial com correções humanas, preservando a lógica do fluxo de revisão.

## Session Store

Responsável por persistir sessões de revisão, estado do processamento, correções e relatórios.

## Supabase Session Store

Implementação opcional de persistência de sessão em Supabase, usada quando habilitada por configuração de ambiente.

---

# Regras importantes do sistema

- O **template DOCX é a fonte de verdade do memorial**.
- O **schema JSON define o contrato de dados do template**.
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
- Supabase
- unittest
- ruff

Dependendo da evolução do projeto, outras bibliotecas auxiliares podem existir no `requirements.txt`.

---

# Execução local

## Instalação de dependências

```bash
pip install -r requirements.txt
```

## Rodando a API

Caso o entrypoint da aplicação seja `app.main:app`, use:

```bash
uvicorn app.main:app --reload
```

Se o projeto estiver usando outro entrypoint, ajuste o comando conforme a estrutura real do backend.

---

# Testes

## Teste específico de renderização do template

```bash
python scripts/test_render_eletrico.py
```

Arquivos gerados por esse script são salvos em:

```text
tests/output/
```

## Rodar toda a suíte de testes

```bash
python -m unittest discover -s tests
```

## Rodar arquivos específicos de teste

Exemplo:

```bash
python -m unittest tests.test_session_store tests.test_supabase_session_store tests.test_api
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

---

# Próximos passos

Os próximos passos do projeto estão concentrados em robustez, previsibilidade e expansão gradual da cobertura do pipeline.

Prioridades atuais:

1. reforçar o ciclo de vida e cleanup dos arquivos temporários
2. tipar melhor os contratos do fluxo de revisão
3. reduzir duplicação interna no pipeline por arquivos
4. ampliar testes end-to-end do fluxo de sessão
5. fortalecer a integração e consistência do session store com Supabase
6. evoluir a cobertura do extraction mapper para os campos ainda pendentes

---

# Observações finais

Este README descreve o estado atual do projeto com foco no memorial elétrico v1.

O sistema já possui uma base funcional de geração automática com revisão manual opcional, mas ainda está em evolução para ganhar mais robustez operacional, melhor tipagem de contratos e maior cobertura de testes.
