# Template elétrico canteiro de obras v1

## Arquivos
- schema.json (contrato do contexto)
- template.docx (Task 2)

## Objetivo
Memorial descritivo elétrico de canteiro de obras. Sem dados do prédio, sem gerador, sem "não inclusos" e sem instalação. Sem BEP, malha no subsolo ou SPDA da edificação.

## Seções condicionais
- `energia.tem_subestacao`: quando falso, a seção 4.2 (subestação) some e o sumário renumera.
- `mt.diametro_eletroduto_pol`: sem valor, os parágrafos de eletroduto de MT saem do documento.
- `mt.secao_cabo_mm2` (com `tipo_cabo`, `temperatura_cabo`, `classe_isolacao`): sem valor, os parágrafos de cabo de MT saem do documento. O alimentador de BT nunca é cabo de MT.
- `equipamentos[].potencia` nulo: só nome e quantidade.
- `quadros[].descricao` nulo: só nome e carga.

## Valores fixos confirmados (CANTEIRO_DEFAULTS)
- `energia.tap_descricao`: Tap 1 – 13.800 V; Tap 2 – 13.200 V; Tap 3 – 12.600 V; Tap 4 – 12.000 V; Tap 5 – 11.400 V.
- `energia.tensao_secundaria`: 380 V entre fases e 220 V entre fases e neutro
- `aterramento.tipo_sistema`: TN-S
- `mt.tensao_kv`: 13,8
- `obra.porcentagem_entre_trafos` e `obra.porcentagem_entre_quadros`: mesmos do elétrico.
Sem default (variam por obra): eletroduto e cabo de MT.

## Quadros
`quadros[].carga_formatada` e `descricao` são preenchidos pelo builder (`QUADRO_DESCRICOES_CONHECIDAS`); o mapper entrega só `nome` e `carga_w`.
