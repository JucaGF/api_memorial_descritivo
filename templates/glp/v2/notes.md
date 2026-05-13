# Template GLP v2 (em desenvolvimento)

## Status

**Schema:** definido em `schema.json`.

**Template DOCX:** **AINDA NÃO AUTORIZADO**. Este arquivo binário precisa ser criado/editado no Microsoft Word com os novos placeholders Jinja antes que a rota `POST /api/v1/memoriais/glp/v2/from-files` possa servir documentos. Enquanto o arquivo `template.docx` desta pasta não existir, a rota v2 (atrás da feature flag `GLP_V2_ENABLED=true`) retorna 503 com `code=glp_v2_template_pending`.

## Diferenças vs GLP v1

GLP v1 (mantido sem alterações) usa campos planos:
- `abastecimento.qtd_tanques` (int — semanticamente "abrigos", nome histórico).
- `ramal.primario_diametro` (string preservando notação original).
- `dimensionamento.{qtd_fogao, qtd_aquecedor, qtd_churrasqueira}` (ints).
- `soma.qtd_pontos_de_utilizacao` (int).
- Sem `valvula`.
- Sem campos de evidência ou conflito.

GLP v2 separa conceitos e adiciona rastreabilidade:

| v1 | v2 |
|---|---|
| `abastecimento.qtd_tanques` (int, semântica = abrigos) | `tanques.{quantidade, qtd_abrigos, tipo, capacidade_kg, fonte_evidencia, conflitos}` — distingue recipientes (P-190) de abrigos. |
| `ramal.primario_diametro` (string crua) | `diametros.tubulacao_principal.{valor, unidade, valor_formatado, valor_original, fonte_evidencia}` — diâmetro normalizado por `app/services/diameter_normalizer.py`. |
| sem campo | `diametros.valvula_esfera.{valor, unidade, valor_formatado, inferido, fonte_evidencia}` — diâmetro da válvula esfera, com flag `inferido` quando deriva da tubulação por falta de evidência explícita. |
| `dimensionamento` + `soma.qtd_pontos_de_utilizacao` | `pontos_utilizacao.{fogao, churrasqueira, aquecedor, outros, total_extraido, total_calculado, conflitos}` — separa por tipo, mantém ambos os totais e detecta divergência. |
| `obra.qtd_apartamentos` (int) | `obra.qtd_apartamentos.{valor, fonte_evidencia, confianca}` — versão estruturada que evita stale value sobrescrever extração fresca. |
| sem campo | `context_version` e `template_version` (constantes `"glp_v2"`) — identificadores que dashboard/chatbot/site usam para selecionar a projeção. |

## Regras de unidade do diâmetro

A unidade do diâmetro é **explícita** (`"in"` ou `"mm"`) e nunca inferida do range numérico. O template **NÃO** deve concatenar `mm` ou `"` depois do placeholder `{{ diametros.tubulacao_principal.valor_formatado }}` — esse valor já inclui o sufixo apropriado, derivado da notação original do projeto. Isso evita o bug histórico onde `1 1/4"` era renderizado como `1.25mm`.

## Regras de tanques

`tanques.quantidade` conta **recipientes/cilindros** instalados (ex: 2 P-190). `tanques.qtd_abrigos` conta abrigos (geralmente 1). Detalhes em legendas, cortes esquemáticos, tabelas de referência ou desenhos auxiliares **não** entram na contagem.

## Regras de pontos

`total_calculado` deve ser igual a `fogao + churrasqueira + aquecedor + outros`. `total_extraido` (quando presente) é o valor lido da tabela quantitativa do projeto. Se os dois diferirem além da tolerância acordada, o pipeline gera `conflitos` com `status=unresolved` e bloqueia a renderização. **Jamais** usar `obra.qtd_apartamentos.valor` como proxy direto de `fogao` ou `churrasqueira` sem evidência explícita; o mapper marca a inferência como `confianca: low` e exige confirmação.

## Casos de teste obrigatórios

- Schema aceita contexto válido com todos os campos obrigatórios.
- Schema rejeita contexto sem `tanques.quantidade`.
- Schema rejeita contexto com `diametros.tubulacao_principal.unidade` fora do enum.
- Schema rejeita contexto sem `context_version`/`template_version`.
- Render falha se `template.docx` v2 ainda não existir (cenário esperado durante a transição).

## Roadmap

1. **Você** cria `templates/glp/v2/template.docx` no Word com os novos placeholders.
2. Ligar `GLP_V2_ENABLED=true` em ambiente de teste.
3. Validar render real com um projeto piloto.
4. Comunicar dashboard/chatbot/site sobre `context_version` para usar a projeção correta.
5. Eventualmente depreciar a rota v1 após período de coexistência.
