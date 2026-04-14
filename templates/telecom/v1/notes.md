# Template telecom v1

## Arquivo

- template.docx
- schema.json

## Objetivo

Definir o contrato de dados para geração automática de memorial descritivo de telecom (v1).

## Motor de renderização

- docxtpl
- sintaxe Jinja2
- contrato de dados baseado em JSON Schema

## Convenções de nomenclatura

Os placeholders são organizados por domínio:

- `documento.*`
- `obra.*`

## Regras do template

- O contexto final deve validar contra o schema.
- O documento final não deve conter placeholders não preenchidos.
- O documento final não deve conter tags Jinja visíveis.
- O objeto raiz não permite propriedades extras (`additionalProperties: false`).
- Todos os campos obrigatórios devem estar preenchidos antes da renderização.
- Esta versão não define seções condicionais.

## Seções condicionais

Não há seções condicionais no schema telecom v1 atual.

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

## Tipos e restrições

- `qtd_apartamentos`, `qtd_lojas` e `qtd_restaurantes` devem ser inteiros maiores ou iguais a zero.

## Casos de teste obrigatórios

- contexto válido com todos os campos obrigatórios
- ausência de `documento.data_atual`
- ausência de campo obrigatório em `obra`
- inclusão de propriedade extra no objeto raiz
- inclusão de propriedade extra em `documento`
- inclusão de propriedade extra em `obra`
- valores negativos em contadores de quantidade
