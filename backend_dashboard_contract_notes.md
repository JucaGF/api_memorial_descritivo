# Backend-dashboard contract notes

## Contexto

O backend passou por iterações de production readiness para:

- healthcheck e readiness;
- configuração por ambiente;
- CORS;
- tratamento seguro de erros;
- validação de upload;
- storage/download/delete de artefatos gerados;
- ciclo de geração, estados e falhas.

Agora o dashboard precisa consumir esses contratos corretamente.

## Objetivo

Garantir que a interface trate corretamente todos os estados e erros relevantes retornados pela API, sem depender de strings frágeis, suposições antigas ou estados enganosos.

## Repositórios

Frontend atual:

- ~/Projects/dashboard-memorial

Backend fonte do contrato:

- ~/Projects/api_memorial_descritivo

O backend deve ser lido para entender contratos, mas não deve ser alterado nesta iteração.

## Estados que o dashboard deve tratar

A nomenclatura exata deve seguir o backend.

Estados esperados ou equivalentes:

- pending
- processing
- succeeded
- failed

O dashboard deve:

- não mostrar geração failed como concluída;
- não permitir download como se fosse válido quando a geração está failed, pending ou processing;
- mostrar ação clara para tentar novamente quando fizer sentido;
- mostrar erro seguro e compreensível;
- manter loading claro enquanto dados ainda estão carregando;
- evitar 0 ou vazio enganoso antes do carregamento real.

## Erros que o dashboard deve tratar

O dashboard deve normalizar respostas de erro da API.

Casos importantes:

- upload com arquivo vazio;
- upload com extensão inválida;
- upload com arquivo grande demais;
- upload com muitos arquivos;
- geração com falha;
- geração em processamento;
- arquivo gerado ausente no storage;
- download indisponível;
- exclusão de item inexistente;
- erro 500 seguro;
- erro de rede;
- API fora do ar.

## Regras de UX

- Mensagem técnica bruta não deve aparecer para o usuário final.
- Stack trace nunca deve aparecer na tela.
- Erro desconhecido deve virar mensagem genérica útil.
- O usuário deve saber o que pode fazer em seguida.
- Quando upload falhar por validação, os arquivos devem permanecer selecionados quando possível.
- Quando geração falhar, a tela deve explicar a falha sem fingir sucesso.
- Quando download falhar, o histórico não deve parecer quebrado sem explicação.
- Quando a API estiver fora do ar, mostrar estado de indisponibilidade claro.

## Fora do escopo

- Não alterar backend.
- Não alterar templates DOCX.
- Não implementar autenticação.
- Não implementar novo design system completo.
- Não fazer refatoração visual ampla.
- Não implementar Playwright E2E completo nesta iteração.
- Não alterar deploy.
