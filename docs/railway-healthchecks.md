# Railway healthchecks

Use `GET /health/ready` como `Healthcheck Path` no Railway.

Esse endpoint representa readiness real da API. Ele retorna:

- `200` quando a aplicação está pronta para receber tráfego
- `503` quando algum check crítico falha

Use `GET /health/live` apenas para confirmar que o processo FastAPI está vivo.

Esse endpoint não valida readiness completa e não deve ser usado sozinho para liberar um deploy novo no Railway.

No estado atual do repositório, a configuração é documental apenas. Não foi adicionado `railway.json`, porque não existe configuração Railway como código aqui e a menor mudança segura é orientar o ajuste manual no painel do Railway.
