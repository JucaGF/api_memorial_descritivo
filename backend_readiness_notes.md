# Backend readiness notes

## Contexto

O sistema já está deployado no Railway para testes básicos, mas ainda não deve ser tratado como pronto para produção.

O frontend passou por uma primeira rodada de correções de UX. Agora a prioridade é preparar a API para deploy mais confiável, especialmente no Railway.

## Objetivo desta iteração

Implementar uma base mínima de production readiness no backend, com endpoints de healthcheck e readiness, testes automatizados e respostas seguras.

## Problema

Atualmente não há garantia clara de que o Railway consiga validar se a API está realmente pronta para receber tráfego antes de ativar um novo deploy.

Também falta um endpoint explícito para diferenciar:
- processo vivo;
- aplicação pronta;
- dependências críticas disponíveis;
- falhas de configuração detectáveis sem expor segredos.

## Resultado esperado

A API deve expor endpoints seguros e testados:

- GET /health/live
- GET /health/ready

O endpoint /health/live deve ser rápido, simples e não depender de serviços externos.

O endpoint /health/ready deve validar dependências críticas locais e configuracionais, retornando 200 quando estiver pronto e 503 quando alguma dependência crítica falhar.

As respostas não podem expor secrets, URLs privadas com tokens, chaves de API, service keys ou dados sensíveis.

## Observações

Não alterar contratos existentes da API.

Não mexer no frontend.

Não alterar lógica de geração de memorial, extração ou renderização além do necessário para verificar disponibilidade de recursos.

Não adicionar dependências novas sem necessidade real.

Priorizar uma solução simples, testável e compatível com Railway.
