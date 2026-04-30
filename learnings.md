# Learnings

Este arquivo acumula aprendizados entre iterações do Ralph/Codex neste repositório.

## Contexto do projeto

Este repositório contém a API do sistema de geração de memoriais descritivos.

O sistema já está deployado no Railway para testes básicos, mas ainda está passando por uma etapa de preparação para produção.

O frontend fica em outro repositório:

- ~/Projects/dashboard-memorial

Nesta iteração, o Ralph deve trabalhar apenas neste repositório backend:

- ~/Projects/api-memorial-descritivo

## Regras permanentes

- Não alterar o frontend a partir deste repositório.
- Não alterar contratos existentes da API sem necessidade explícita.
- Não quebrar endpoints já usados pelo dashboard.
- Não mexer em templates DOCX sem que a story peça isso diretamente.
- Não alterar migrations ou schema de banco sem necessidade explícita.
- Não expor secrets, tokens, service keys, URLs com credenciais, senhas ou variáveis sensíveis em respostas HTTP.
- Preferir mudanças pequenas, testáveis e revisáveis.
- Sempre criar ou atualizar testes automatizados quando alterar comportamento da API.
- Sempre rodar o verificador do projeto antes de considerar uma iteração concluída.

## Aprendizados vindos do dashboard

O frontend passou por uma rodada de UX focada em:

- histórico de memoriais gerados;
- detalhe da geração;
- navegação mobile;
- loading de estatísticas;
- upload mantendo arquivos após erro;
- acessibilidade básica.

Esses fluxos dependem da estabilidade dos endpoints do backend. Portanto, nesta etapa do backend, qualquer alteração precisa preservar compatibilidade com o dashboard.

## Objetivo da próxima iteração

A próxima iteração deve focar em production readiness mínimo da API.

Prioridades:

1. Criar endpoint de liveness.
2. Criar endpoint de readiness.
3. Separar processo vivo de aplicação pronta para receber tráfego.
4. Validar dependências críticas de forma segura.
5. Não fazer chamadas externas pesadas ou lentas sem timeout.
6. Garantir que falhas de readiness retornem 503.
7. Garantir que respostas de health não exponham informações sensíveis.
8. Documentar como configurar o healthcheck no Railway.

## Diretriz para healthchecks

O endpoint de liveness deve ser simples e rápido.

Ele deve responder se o processo FastAPI está vivo, sem depender de:

- banco;
- Supabase;
- OpenAI;
- filesystem pesado;
- templates;
- rede externa.

O endpoint de readiness deve responder se a aplicação está pronta para receber tráfego.

Ele pode verificar, conforme fizer sentido na estrutura real do projeto:

- configuração obrigatória;
- existência de templates e schemas necessários;
- diretórios locais necessários;
- capacidade básica de inicialização de serviços internos;
- dependências críticas, sem expor valores sensíveis.

## Cuidados com Railway

O Railway pode usar um healthcheck para decidir quando um deploy novo está pronto para ser ativado. Por isso, o endpoint recomendado para deploy deve ser o readiness, não apenas o liveness. O liveness diz que o processo está vivo; o readiness diz que a aplicação está pronta para receber tráfego. 

## Cuidados com testes

Os testes de readiness não devem depender de serviços externos reais.

Para simular falhas, prefira:

- monkeypatch;
- mocks;
- fixtures temporárias;
- alteração controlada de configuração;
- paths temporários.

Os testes devem cobrir pelo menos:

1. /health/live retornando 200.
2. /health/ready retornando 200 quando tudo está ok.
3. /health/ready retornando 503 quando um check crítico falha.
4. resposta de health não expondo secrets conhecidos.

## Restrições desta iteração

Não transformar esta rodada em uma auditoria completa de segurança.

Não implementar:

- autenticação;
- rate limit;
- observabilidade completa;
- Sentry;
- OpenTelemetry;
- sistema de logs estruturados completo;
- refatoração arquitetural ampla;
- mudanças no fluxo de geração.

Esses pontos podem virar iterações futuras.


## Story RDY-001 concluída

Tentativa bem-sucedida: 1

## Iteração RDY-002: configuração segura e CORS

A iteração anterior adicionou healthcheck e readiness check.

A próxima prioridade é preparar a API para ambientes diferentes:

- local;
- test;
- production.

A API deve ter uma fonte clara de configuração, evitando variáveis lidas de forma espalhada e implícita pelo código.

Cuidados principais:

1. Não usar CORS aberto em produção.
2. Não aceitar fallback inseguro em produção.
3. Não expor secrets em logs, respostas HTTP ou mensagens de erro.
4. Validar variáveis obrigatórias de produção no startup ou em camada de configuração.
5. Manter o ambiente local simples de rodar.
6. Manter testes independentes de variáveis reais do Railway.
7. Não quebrar o healthcheck criado na iteração anterior.
8. Não quebrar endpoints usados pelo dashboard.

Diretriz para CORS:

- Em desenvolvimento local, permitir origens locais do dashboard, como localhost e 127.0.0.1.
- Em produção, permitir apenas a URL real do dashboard.
- A origem do dashboard deve vir de variável de ambiente, não hardcoded em código de produção.
- Se a aplicação ainda não tiver a URL final do dashboard em produção, documentar a variável necessária no Railway.

Diretriz para configuração:

- Antes de criar uma nova abordagem, verificar se o projeto já tem módulo de settings/config.
- Se já houver uma abordagem, estender a abordagem existente.
- Se não houver, criar uma camada simples e testável.
- Não adicionar pydantic-settings sem necessidade.
- Se pydantic-settings já existir no projeto, pode ser usado.
- Se for adicionar nova dependência, justificar claramente.


## Story RDY-002 concluída

Tentativa bem-sucedida: 1

## Iteração RDY-003: erros, logs e respostas seguras

As iterações anteriores adicionaram:

- healthcheck e readiness check;
- configuração segura por ambiente;
- CORS explícito.

A próxima prioridade é padronizar erros e logs para produção.

Objetivo principal:

- o usuário deve receber erros claros, consistentes e seguros;
- o desenvolvedor deve ter logs suficientes para diagnosticar problemas;
- nenhuma resposta HTTP deve vazar stack trace, segredo, variável sensível, path interno desnecessário ou detalhe bruto de exceção.

Regras permanentes para esta iteração:

1. Não alterar contratos principais da API sem necessidade.
2. Não alterar frontend.
3. Não alterar templates DOCX.
4. Não alterar banco.
5. Não adicionar Sentry, OpenTelemetry, APM ou dependência externa de observabilidade.
6. Usar logging padrão do Python, salvo se o projeto já tiver outra solução.
7. Não engolir exceções silenciosamente.
8. Não retornar exception.message bruto para o usuário em erro 500.
9. Logs podem ter detalhes técnicos, mas não podem conter secrets.
10. Respostas HTTP devem seguir um formato previsível.
11. Testes devem verificar que erros internos não vazam detalhes sensíveis.
12. Healthcheck e readiness devem continuar funcionando.

Diretriz para respostas de erro:

- Erros esperados de validação ou regra de negócio devem retornar mensagem útil.
- Erros internos inesperados devem retornar mensagem genérica.
- O corpo da resposta deve ser consistente o suficiente para o frontend tratar.
- A resposta deve incluir algum identificador de erro ou request id se for viável implementar de forma simples.

Diretriz para logs:

- Registrar erros internos com stack trace no log.
- Registrar contexto útil, como path, método HTTP e tipo do erro.
- Não registrar corpo de upload, arquivos, tokens ou secrets.
- Não registrar variáveis de ambiente inteiras.
- Não imprimir chaves de API, service role keys, URLs com credenciais ou Authorization headers.


## Story RDY-003 concluída

Tentativa bem-sucedida: 1


## Story RDY-004 concluída

Tentativa bem-sucedida: 1


## Iteração RDY-005: storage persistido dos memoriais gerados

Mapeamento inspecionado nesta iteração:

- Os endpoints públicos de histórico persistido ficam em `app/api/routes.py`:
  - `GET /api/v1/memoriais`
  - `GET /api/v1/memoriais/{memorial_id}`
  - `GET /api/v1/memoriais/{memorial_id}/download`
  - `DELETE /api/v1/memoriais/{memorial_id}`
  - `POST /api/v1/memoriais/{memorial_type}/from-files/persist`
- A metadata dos memoriais persistidos é salva na tabela Supabase `generated_memorials`.
- O arquivo DOCX persistido é salvo em bucket Supabase Storage.
- O fluxo atual de persistência gera o DOCX primeiro em arquivo temporário local, depois faz upload para o bucket e remove o temporário ao final.
- Portanto, o filesystem local continua sendo apenas transitório para renderização; ele não deve ser a base de persistência em produção.
- O registro salvo em metadata contém `storage_bucket` e `storage_path`, e o `storage_path` esperado segue o formato determinístico `{tipo}/{id}/{filename_oficial}`.
- O endpoint de download primeiro localiza a metadata pelo `memorial_id` e depois resolve o acesso ao artefato via storage.
- O endpoint de exclusão primeiro localiza a metadata, depois remove o artefato no storage e só então remove a metadata para evitar estado enganoso.
- A configuração do storage persistido passou a ser tratada de forma central em `app.config`, em vez de múltiplos `os.getenv` espalhados no store.
- Em `production`, o backend deve exigir configuração explícita de `GENERATED_MEMORIALS_BUCKET`, `SUPABASE_URL` e `SUPABASE_KEY` para os memoriais persistidos.
- Em `local` e `test`, o bucket pode continuar com default simples, mas o contrato persistido ainda depende de Supabase quando esses endpoints forem usados.


## Story RDY-005 concluída

Tentativa bem-sucedida: 1

## Iteração RDY-006: ciclo de geração, estados e falhas

A próxima etapa de production readiness é validar o ciclo completo de geração.

Objetivo:

- garantir que cada geração tenha estado confiável;
- garantir que falhas de extração, mapeamento, renderização, storage ou background task sejam refletidas corretamente;
- impedir que geração falha apareça como concluída;
- impedir download de artefato inexistente, parcial ou associado a geração falha;
- melhorar testes de transições e falhas.

Diretrizes:

1. Trabalhar somente no backend.
2. Não alterar frontend.
3. Não alterar templates DOCX.
4. Não adicionar fila externa.
5. Não adicionar autenticação.
6. Não criar arquitetura grande se o projeto atual puder ser endurecido com mudanças pequenas.
7. Preservar contratos já usados pelo dashboard quando possível.
8. Usar erros seguros e previsíveis.
9. Registrar falhas com logging adequado.
10. Rodar verify.py antes de concluir.

### Mapeamento inspecionado na tentativa 1 de RDY-006

- O fluxo síncrono persistido parte de `POST /api/v1/memoriais/{memorial_type}/from-files/persist` em `app/api/routes.py`.
- Esse endpoint gera o DOCX localmente em arquivo temporário, delega a persistência final para `app/services/generated_memorial_store.py` e sempre remove o temporário no `finally`.
- Antes desta tentativa, `create_generated_memorial` fazia upload do artefato e inseria a metadata já com `status=ready`, sem estado intermediário explícito durante a persistência.
- Antes desta tentativa, o download persistido aceitava qualquer registro com `storage_bucket` e `storage_path` válidos, sem bloquear registros `processing` ou `failed`.
- O histórico persistido já expõe `status` via `GeneratedMemorialResponse`, então endurecer a transição no store preserva o contrato existente com menor risco do que criar um modelo paralelo.
- O fluxo de revisão por sessão já tinha estados explícitos (`processing`, `pending_review`, `failed`) e tratamento de falha em background; a lacuna principal desta tentativa estava no ciclo dos memoriais persistidos.


## Story RDY-006 concluída

Tentativa bem-sucedida: 1
