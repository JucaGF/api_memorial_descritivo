# Template gas natural v1

## Arquivos

- MODELO MEMORIAL DE GÁS NATURAL.docx
- schema.json

## Objetivo

Definir o contrato de dados para geração automática do memorial descritivo de gás natural (v1).

## Motor de renderização

- docxtpl
- sintaxe Jinja2
- contrato de dados baseado em JSON Schema

## Convenções de nomenclatura

Os placeholders são organizados por domínio:

- documento.*
- obra.*
- crm.*
- dimensionamento.*
- soma.*
- ramal.*
- valvula.*
- numero.*
- teto_ou_piso

## Regras do template

- O contexto final deve validar contra o schema antes da renderização.
- O objeto raiz não permite propriedades extras (additionalProperties: false).
- Os objetos internos também não permitem propriedades extras.
- O documento final não deve conter placeholders não preenchidos.
- O documento final não deve conter tags Jinja visíveis.
- Esta versão não define blocos condicionais Jinja ({% if %}) no template.

## Seções condicionais

Não há seções condicionais identificadas no template gas natural v1 atual.

## Campos obrigatórios mínimos

### documento

- documento.data_atual

### obra

- obra.numero_cadastro
- obra.construtora
- obra.nome
- obra.localizacao
- obra.tipo_edificacao
- obra.tipologia
- obra.qtd_apartamentos
- obra.qtd_lojas
- obra.qtd_restaurantes

### crm

- crm.pavimento

### dimensionamento

- dimensionamento.qtd_fogao
- dimensionamento.qtd_aquecedor
- dimensionamento.qtd_churrasqueira

### soma

- soma.qtd_pontos_de_utilizacao

### ramal

- ramal.primario_diametro
- ramal.primario_material
- ramal.primario_pavimento

### valvula

- valvula.esfera_diametro

### numero

- numero.prancha

### raiz

- teto_ou_piso

## Tipos e restricoes

- obra.qtd_apartamentos, obra.qtd_lojas e obra.qtd_restaurantes: integer >= 0.
- dimensionamento.qtd_fogao, dimensionamento.qtd_aquecedor e dimensionamento.qtd_churrasqueira: integer >= 0.
- soma.qtd_pontos_de_utilizacao: integer >= 0.
- ramal.primario_diametro: number >= 0.
- teto_ou_piso: string.

## Placeholders identificados no DOCX

Placeholders encontrados por inspeção do XML do documento:

- documento.data_atual
- obra.numero_cadastro
- obra.construtora
- obra.nome
- obra.localizacao
- obra.tipo_edificacao
- obra.tipologia
- obra.qtd_apartamentos
- obra.qtd_lojas
- obra.qtd_restaurantes
- crm.pavimento
- dimensionamento.qtd_fogao
- dimensionamento.qtd_aquecedor
- dimensionamento.qtd_churrasqueira
- soma.qtd_pontos_de_utilizacao
- ramal.primario_diametro
- ramal.primario_material
- ramal.primario_pavimento
- numero.prancha
- teto_ou_piso
- valvula.esfera_diametro (esperado pelo schema)

Observacao tecnica:

- No XML extraido do DOCX, o placeholder de valvula aparece fragmentado como "v a lvula.esfera_diametro" por quebra de runs do Word. Isso pode impedir renderizacao correta por docxtpl e deve ser validado com teste de render.

## Casos de teste obrigatorios

- contexto valido com todos os campos obrigatorios
- ausencia de documento.data_atual
- ausencia de campo obrigatorio em cada objeto aninhado
- inclusao de propriedade extra no objeto raiz
- inclusao de propriedade extra em objetos internos
- valores negativos em campos inteiros/numero com minimum 0
- render do DOCX sem placeholders residuais
- validacao especifica do placeholder valvula.esfera_diametro na saida renderizada
