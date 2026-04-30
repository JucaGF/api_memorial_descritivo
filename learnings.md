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
