# Template elétrico v1

## Arquivo
- template.docx

## Objetivo
Template DOCX para geração automática de memorial descritivo elétrico.

## Motor de renderização
- docxtpl
- sintaxe Jinja2
- seções condicionais com `{%p if %}` e `{%p endif %}`

## Convenções de nomenclatura
Os placeholders são organizados por domínio:

- `documento.*`
- `obra.*`
- `energia.*`
- `mt.*`
- `aterramento.*`
- `gerador.*`
- `nao_inclusos.*`
- `instalacao.*`

## Regras do template
- O documento final não deve conter placeholders não preenchidos.
- O documento final não deve conter tags Jinja visíveis.
- O documento final não deve conter observações internas.
- A numeração das seções está fixa no texto.
- O sumário atual é manual/estático.
- O comportamento da seção 4.4 será ignorado nesta versão.

## Seções condicionais
### `energia.tem_subestacao`
Controla:
- texto alternativo da seção 4.1
- exibição da seção 4.2
- exibição da seção 4.2.1
- trecho de MT em 4.5
- trecho de barramento MT em 4.7

### `gerador.tipo_atendimento`
Valores aceitos:
- `edificio`
- `condominio`
- `parcial`

Se for `parcial`, exigir:
- `gerador.circuitos_atendidos`

### `nao_inclusos.*`
Cada booleano controla uma linha da seção 4.12:
- `cpct`
- `cftv`
- `alarme_patrimonial`
- `sonorizacao`
- `alarme_incendio`
- `automacao`

## Campos obrigatórios mínimos
### documento
- `documento.data_atual`

### obra
- `obra.numero_cadastro`
- `obra.construtora`
- `obra.nome`
- `obra.localizacao`
- `obra.tipo_edificacao`
- `obra.tipologia`
- `obra.qtd_apartamentos`
- `obra.qtd_lojas`
- `obra.qtd_restaurantes`
- `obra.porcentagem_entre_trafos`
- `obra.porcentagem_entre_quadros`

### energia
- `energia.tem_subestacao`

Se `energia.tem_subestacao = true`, exigir também:
- `energia.tipo_subestacao`
- `energia.potencia_transformador_kva`
- `energia.tap_descricao`
- `energia.tensao_secundaria`

### mt
Usado no template atual:
- `mt.tensao_kv`
- `mt.diametro_eletroduto_pol`
- `mt.tipo_cabo`
- `mt.temperatura_cabo`
- `mt.classe_isolacao`
- `mt.secao_cabo_mm2`

### aterramento
- `aterramento.qtd_hastes`
- `aterramento.secao_cabo_cobre_mm2`
- `aterramento.tipo_sistema`
- `aterramento.secao_cabo_malha_mm2`
- `aterramento.local_bep`

### gerador
- `gerador.qtd`
- `gerador.potencia_kva`
- `gerador.tipo_atendimento`

Se `gerador.tipo_atendimento = parcial`, exigir:
- `gerador.circuitos_atendidos`

### nao_inclusos
- `nao_inclusos.cpct`
- `nao_inclusos.cftv`
- `nao_inclusos.alarme_patrimonial`
- `nao_inclusos.sonorizacao`
- `nao_inclusos.alarme_incendio`
- `nao_inclusos.automacao`

### instalacao
- `instalacao.perfilado_tipo`

## Casos de teste obrigatórios
- com subestação
- sem subestação
- gerador atendendo edifício
- gerador atendendo condomínio
- gerador com atendimento parcial
- seção 4.12 sem itens marcados
- seção 4.12 com múltiplos itens marcados