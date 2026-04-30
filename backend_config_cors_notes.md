# Backend config and CORS notes

## Contexto

A API já possui healthcheck e readiness check após a iteração RDY-001.

Agora a prioridade é melhorar a configuração por ambiente e CORS.

O frontend está em outro repositório:

- ~/Projects/dashboard-memorial

O backend está neste repositório:

- ~/Projects/api-memorial-descritivo

## Objetivo

Implementar uma base segura e testável de configuração por ambiente e CORS.

## Problemas que esta iteração deve resolver

1. A API precisa saber em qual ambiente está rodando.
2. A API precisa validar variáveis obrigatórias em produção.
3. A configuração de CORS precisa ser explícita e segura.
4. O ambiente local precisa continuar simples.
5. Os testes não podem depender de variáveis reais do Railway.
6. O readiness check não deve expor secrets nem quebrar por causa de configuração local aceitável.

## Ambientes esperados

### local

Ambiente de desenvolvimento na máquina.

Deve permitir frontend local, por exemplo:

- http://localhost:5173
- http://127.0.0.1:5173
- http://localhost:3000
- http://127.0.0.1:3000

### test

Ambiente de testes automatizados.

Deve usar configuração previsível e isolada.

Não deve depender de secrets reais.

### production

Ambiente do Railway.

Deve exigir configuração explícita para origem do dashboard.

Não deve permitir CORS aberto.

Não deve usar fallback inseguro.

## Variáveis sugeridas

A implementação deve avaliar a estrutura atual do projeto antes de fixar nomes finais.

Sugestões:

- APP_ENV
- CORS_ALLOWED_ORIGINS
- FRONTEND_URL
- SUPABASE_URL
- SUPABASE_ANON_KEY
- SUPABASE_SERVICE_ROLE_KEY
- OPENAI_API_KEY

Nem todas precisam ser obrigatórias em todos os ambientes.

## Regras

Não expor valores sensíveis.

Não imprimir secrets em logs.

Não retornar secrets em endpoints de health.

Não quebrar endpoints existentes.

Não alterar frontend.

Não alterar Railway diretamente nesta iteração, exceto documentação.

## Resultado esperado

A aplicação deve ter uma forma clara de carregar e validar configurações.

O CORS deve ser configurado a partir dessa configuração.

A produção deve falhar de forma explícita se variáveis críticas estiverem ausentes.

O local e os testes devem continuar funcionando sem exigir secrets reais.
