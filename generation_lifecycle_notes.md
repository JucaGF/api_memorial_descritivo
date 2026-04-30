# Generation lifecycle notes

## Contexto

O backend já passou por iterações de production readiness para:

- healthcheck e readiness;
- configuração por ambiente;
- CORS;
- tratamento seguro de erros;
- validação e contrato de upload;
- persistência/download/exclusão de artefatos gerados.

Agora a prioridade é endurecer o ciclo completo de geração.

## Objetivo

Garantir que cada geração tenha um estado confiável e que falhas em qualquer etapa sejam refletidas de forma previsível para API, logs, histórico e download.

## Problemas que esta iteração deve prevenir

1. Geração falhar mas aparecer como concluída.
2. Geração falhar em background task e o erro sumir.
3. Geração ficar presa indefinidamente em estado de processamento.
4. Metadata ser criada sem artefato final baixável.
5. Artefato ser salvo sem metadata consistente.
6. Falha de renderização deixar arquivo parcial como se fosse válido.
7. Falha de extração/mapeamento retornar erro inseguro ou pouco útil.
8. Retry manual ou nova tentativa reaproveitar estado inválido.
9. Download tentar servir arquivo de geração falha.
10. Histórico mostrar geração em estado incorreto.

## Estados sugeridos

Não criar uma arquitetura grande se o projeto já tiver outro modelo.

Estados possíveis, se fizerem sentido para o projeto:

- pending
- processing
- succeeded
- failed

Opcionalmente:

- cancelled
- expired

O importante é que o sistema tenha uma transição previsível.

## Regras de transição sugeridas

- Uma geração recém-criada deve começar como pending ou processing.
- Ao iniciar processamento real, deve ir para processing.
- Ao concluir renderização e persistência do artefato, deve ir para succeeded.
- Se qualquer etapa crítica falhar, deve ir para failed.
- Uma geração failed deve guardar um erro seguro e legível.
- Uma geração succeeded deve ter referência válida ao artefato.
- Uma geração failed não deve permitir download de DOCX inexistente ou parcial.
- Uma geração processing antiga demais deve ter comportamento definido ou ser detectável.

## Erros

FastAPI HTTPException deve continuar sendo usada para erros esperados de cliente, como geração inexistente, download inválido ou estado incompatível. Falhas internas devem ser tratadas pelo sistema de erro seguro já criado.

## Fora do escopo

- Não implementar fila externa.
- Não implementar Celery, Redis Queue, Dramatiq ou similar.
- Não implementar autenticação.
- Não alterar frontend.
- Não alterar templates DOCX.
- Não alterar visual do documento gerado.
- Não implementar retry automático complexo.
- Não implementar observabilidade avançada.
