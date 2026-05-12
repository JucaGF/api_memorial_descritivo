# Template GLP v1

## Arquivos

- template.docx
- schema.json

## Objetivo

Definir o contrato de dados para geração automática do memorial descritivo de GLP (v1).

## Motor de renderização

- docxtpl
- sintaxe Jinja2
- contrato de dados baseado em JSON Schema

## Convenções de nomenclatura

Os placeholders são organizados por domínio:

- documento.*
- obra.*
- abastecimento.*
- dimensionamento.*
- soma.*
- ramal.*
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

Não há seções condicionais identificadas no template GLP v1 atual.

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

### abastecimento

- abastecimento.qtd_tanques
- abastecimento.pavimento

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

### numero

- numero.prancha

### raiz

- teto_ou_piso

## Tipos e restricoes

- obra.qtd_apartamentos, obra.qtd_lojas e obra.qtd_restaurantes: integer >= 0.
- abastecimento.qtd_tanques: integer >= 1.
- dimensionamento.qtd_fogao, dimensionamento.qtd_aquecedor e dimensionamento.qtd_churrasqueira: integer >= 0.
- soma.qtd_pontos_de_utilizacao: integer >= 0.
- ramal.primario_diametro: string, preservando a notação indicada no projeto.
- teto_ou_piso: string.

## Diferenças em relação ao gas_natural v1

- GLP usa `abastecimento` (qtd_tanques, pavimento) no lugar de `crm` (pavimento).
- GLP não possui `valvula` (esfera_diametro), que é específico do gás natural canalizado.

## Casos de teste obrigatorios

- contexto valido com todos os campos obrigatorios
- render do DOCX sem placeholders residuais
