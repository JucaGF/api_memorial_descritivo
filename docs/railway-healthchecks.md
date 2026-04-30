# Railway healthchecks

Use `GET /health/ready` como `Healthcheck Path` no Railway.

Esse endpoint representa readiness real da API. Ele retorna:

- `200` quando a aplicação está pronta para receber tráfego
- `503` quando algum check crítico falha

Use `GET /health/live` apenas para confirmar que o processo FastAPI está vivo.

Esse endpoint não valida readiness completa e não deve ser usado sozinho para liberar um deploy novo no Railway.

No estado atual do repositório, a configuração é documental apenas. Não foi adicionado `railway.json`, porque não existe configuração Railway como código aqui e a menor mudança segura é orientar o ajuste manual no painel do Railway.

## Variáveis para RDY-002

Configure no Railway:

- `APP_ENV=production`
- `CORS_ALLOWED_ORIGINS=https://dashboard.seu-dominio.com`

Se existir mais de uma origem válida, use lista separada por vírgula, por exemplo:

`CORS_ALLOWED_ORIGINS=https://dashboard.seu-dominio.com,https://preview.seu-dominio.com`

Regras atuais:

- em `production`, a API falha na inicialização se `CORS_ALLOWED_ORIGINS` estiver ausente ou vazio
- espaços extras e entradas vazias são ignorados
- não use `*` nem CORS aberto em produção
- em `local` e `test`, a API aceita origens locais padrão do dashboard para manter desenvolvimento e testes simples
