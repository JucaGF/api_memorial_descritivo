# Backend errors and logs notes

## Contexto

O backend já possui uma base inicial de production readiness:

- liveness;
- readiness;
- configuração por ambiente;
- CORS explícito.

Agora a prioridade é padronizar tratamento de erros e logging.

## Objetivo

Criar uma base mínima e segura para erros e logs em produção.

## Problemas que esta iteração deve resolver

1. Erros internos não podem vazar stack trace para o usuário.
2. Erros internos não podem retornar mensagens brutas de exceção.
3. Respostas de erro devem ter formato consistente.
4. Logs devem ajudar debug sem expor secrets.
5. Erros esperados devem continuar retornando status codes corretos.
6. Validações do FastAPI/Pydantic devem continuar legíveis para o frontend.
7. Healthcheck e readiness não podem ser quebrados.
8. O código não deve ganhar try/except espalhado sem critério.

## Formato sugerido de erro

Avaliar a estrutura atual antes de implementar.

Um formato possível:

{
  "error": {
    "code": "internal_server_error",
    "message": "Erro interno ao processar a requisição.",
    "request_id": "..."
  }
}

Para erros de validação:

{
  "error": {
    "code": "validation_error",
    "message": "Dados inválidos na requisição.",
    "details": [...]
  }
}

Para HTTPException conhecida:

{
  "error": {
    "code": "not_found",
    "message": "..."
  }
}

O formato final pode variar conforme a estrutura existente do projeto, mas deve ser consistente.

## Request id

Implementar request id somente se for simples e seguro.

Preferência:

- aceitar X-Request-ID se vier do cliente;
- gerar um UUID quando não vier;
- devolver X-Request-ID na resposta;
- incluir request_id nos logs.

Não transformar isso em tracing completo.

## Logging

Usar logging padrão do Python, salvo se já existir outra abordagem no projeto.

O logger deve ser configurado de forma simples.

Boas práticas:

- logger por módulo com logging.getLogger(__name__);
- nível configurável por ambiente;
- INFO para eventos normais relevantes;
- WARNING para falhas esperadas ou recuperáveis;
- ERROR/EXCEPTION para falhas internas;
- nunca logar secrets.

## Dados sensíveis que nunca devem aparecer

- OPENAI_API_KEY
- SUPABASE_SERVICE_ROLE_KEY
- SUPABASE_ANON_KEY
- DATABASE_URL com credenciais
- Authorization
- Cookie
- Set-Cookie
- tokens
- senhas
- conteúdo integral de arquivos enviados
- conteúdo integral de DOCX/PDF enviado
- variáveis de ambiente completas

## Escopo

Esta iteração é uma base mínima.

Não implementar:

- Sentry;
- OpenTelemetry;
- tracing distribuído;
- dashboard de logs;
- alertas;
- rate limit;
- autenticação;
- autorização;
- auditoria completa de segurança.
