# Memorial Elétrico de Canteiro de Obras v1 — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar o tipo `eletrico-canteiro` v1, que gera o memorial elétrico de **canteiro de obras** a partir das plantas de canteiro, sem exigir dados do prédio.

**Architecture:** Trilha própria, no mesmo padrão explícito por tipo de `telecom`, `gas-natural` e `glp` (sem registry genérico). Template, schema, validator, renderer, mapper e estratégia de LLM são próprios do canteiro. Os helpers do elétrico (`_extract_construtora`, `_extract_numero_cadastro`, constantes de queda de tensão) são **reaproveitados por import**, não copiados. O tipo entra em todos os registros por tipo do fluxo persistido/dashboard.

**Tech Stack:** FastAPI, jsonschema, docxtpl, python-docx, PyMuPDF, unittest, OpenAI Responses API (`responses.parse` com Pydantic).

**Spec:** este plano é a spec. Fontes:
- memorial de exemplo do engenheiro: `MEMO ELÉTRICO CANTEIRO DE OBRA_14-11-2026.doc` (MAKAI, com anotações "Fixo"/"Variável"/"Muda conforme cadastro");
- plantas reais: `01_` e `02_CANTEIRO OBRA BOTHANIC_V05_03-11-2026-Engpred.pdf`;
- decisões do engenheiro em 16/11/2026, nas respostas 1 a 5 abaixo;
- avaliação de `docs/plans/2026-04-10-gas-natural-v1-implementation.md`, que é o molde, com 5 ajustes.

## Decisões do engenheiro (16/11/2026)

1. **Dados do prédio:** retirar. O memorial de canteiro **não** tem `tipo_edificacao`, `tipologia`, `qtd_apartamentos`, `qtd_lojas` nem `qtd_restaurantes`.
2. **Equipamentos (seção 7):** lista montada a partir da planta, com nome, potência e quantidade. Substitui a lista fixa com "(xx)".
3. **Quadros (seção 8):** listar os quadros reais da planta, com a carga de cada um.
4. **BEP / malha no subsolo / SPDA da edificação:** não se aplicam ao canteiro. Remover do texto de proteção contra choques.
5. **Tensão de MT** quando a planta não informar: **13,8 kV**.

## Valores assumidos do memorial de exemplo (confirmar com o engenheiro antes do merge)

Vêm do texto do exemplo e entram como default no `context_builder`. São trocáveis sem mexer no código além da constante:

| Campo | Default | Origem no exemplo |
|---|---|---|
| `mt.diametro_eletroduto_pol` | `4` | "eletroduto de aço galvanizado… bitola de 4”" |
| `mt.secao_cabo_mm2` | `35` | "cabos EPR/XLPE… 8,7/15KV, secção 35mm²" |
| `mt.tipo_cabo` / `mt.temperatura_cabo` / `mt.classe_isolacao` | `"EPR/XLPE"` / `90` / `"8,7/15"` | idem |
| `energia.tap_descricao` | `"Tap 1 – 13.800 V; Tap 2 – 13.200 V; Tap 3 – 12.600 V; Tap 4 – 12.000 V; Tap 5 – 11.400 V."` | seção da subestação |
| `energia.tensao_secundaria` | `"380 V entre fases e 220 V entre fases e neutro"` | idem |
| `aterramento.tipo_sistema` | `"TN-S"` | seção de proteção contra choques |

**Texto novo do item de proteção contra choques** (substitui o parágrafo do BEP, decisão 4; o engenheiro precisa aprovar a redação):

> Os condutores terra dos quadros de distribuição do canteiro deverão ser conectados à malha de aterramento do canteiro, composta de {{ aterramento.qtd_hastes }} hastes do tipo copperweld de 5/8"x2.400mm, interligadas por cabo de cobre nu de {{ aterramento.secao_cabo_cobre_mm2 }} mm² através de conector GTDU ou solda exotérmica. O número de hastes poderá ser ampliado até que a resistência da malha não ultrapasse 10 ohms em qualquer época do ano.

## Global Constraints

- Identificador do tipo na URL e no banco: `eletrico-canteiro`. Sufixo Python: `eletrico_canteiro_v1`. Diretório do template: `templates/eletrico_canteiro/v1/`.
- Nome exibido: `Memorial Elétrico Canteiro de Obras`. Arquivo salvo: `memorial_eletrico_canteiro_v1.docx`. Versão de template e contexto: `eletrico_canteiro_v1`.
- Mensagem de validação: `Payload invalido para o memorial eletrico canteiro v1.`
- O DOCX é a fonte da estrutura final; `schema.json` é o contrato; a geração final é determinística. A LLM só extrai dados e nunca escreve texto do memorial.
- O documento renderizado não pode conter Jinja nem marcadores internos (`assert_no_jinja_left` e `assert_no_internal_markers_left`, que já existem).
- Nenhuma mudança de comportamento em `eletrico`, `telecom`, `gas-natural`, `glp` ou `glp_v2`. A suíte completa (hoje 411 testes passando) continua verde.
- Sem migração de banco: `memorial_type` não tem CHECK constraint (conferido em `migrations/`).
- Commits sem linhas de coautoria e sem "Generated with".
- Testes: `python -m unittest <módulo>`, como em `AGENTS.md` §9.
- Trabalhar no branch `feat/eletrico-canteiro-v1`, criado a partir do branch deste plano (`docs/plano-eletrico-canteiro-v1`, que sai de `main`).

## Review Focus

1. **Diagramas repetidos entre pranchas.** As duas plantas do Bothanic trazem os mesmos 6 diagramas de quadro. O esperado é 6 quadros, não 12. Teste: `test_canteiro_mapper_dedupes_quadros_repeated_across_sheets` (Task 4).
2. **Carga com separador de milhar e espaçamento variável** (`Q.G.B.T. = 89.088 W`, `Q.D.L/T TORRE = 12.714W`, `Q.D.STAND= 9.170 W`). O esperado é 89088, 12714 e 9170, nunca 89.088. Teste: `test_canteiro_mapper_parses_brazilian_thousands_in_quadro_loads` (Task 4).
3. **Símbolo de legenda confundido com dado.** A regra de aterramento do elétrico lê "TT" da legenda como sistema TT. O canteiro não pode herdar isso e deve ficar com o default TN-S. Teste: `test_canteiro_mapper_does_not_infer_tipo_sistema_from_legend` (Task 4).
4. **Equipamento sem potência** (mini guincho, elevador cremalheira). O documento não pode mostrar "None" nem "()". Teste: `test_render_canteiro_equipment_without_potencia_has_no_placeholder_text` (Task 2).
5. **Canteiro sem subestação.** A seção 4.2 some e o sumário renumera, sem buracos. Teste: `test_render_canteiro_without_subestacao_omits_section_and_renumbers` (Task 2).

---

### Task 1: Contrato — schema, fixture real, validator e context builder

**Files:**
- Create: `templates/eletrico_canteiro/v1/schema.json`
- Create: `templates/eletrico_canteiro/v1/notes.md`
- Create: `tests/fixtures/eletrico_canteiro_bothanic_expected.json`
- Modify: `app/services/memorial_validator.py` (junto de `load_eletrico_v1_schema`, linha 47)
- Modify: `app/services/context_builder.py` (depois de `build_memorial_eletrico_v1_context`, linha 46)
- Test: `tests/test_memorial_validator.py`, `tests/test_context_builder.py`

**Interfaces:**
- Produces:
  - `ELETRICO_CANTEIRO_V1_SCHEMA_PATH`
  - `load_eletrico_canteiro_v1_schema() -> dict[str, Any]`
  - `validate_memorial_eletrico_canteiro_v1_context(context: dict[str, Any]) -> None`, que levanta `MemorialValidationError` como os demais
  - `build_memorial_eletrico_canteiro_v1_context(input_payload: dict[str, Any]) -> dict[str, Any]`
  - constantes `CANTEIRO_DEFAULTS: dict[str, dict[str, Any]]` e `QUADRO_DESCRICOES_CONHECIDAS: dict[str, str]`

**Forma do schema** (`additionalProperties: false` em todo nível, como no elétrico):
- `documento.data_atual`: string, obrigatório.
- `obra`: `numero_cadastro`, `construtora`, `nome` e `localizacao` (strings) obrigatórios; `porcentagem_entre_trafos` e `porcentagem_entre_quadros` (strings) obrigatórios. **Sem** os campos do prédio (decisão 1).
- `energia`: igual ao elétrico (`tem_subestacao` obrigatório e o `allOf` if/then copiado de `templates/eletrico/v1/schema.json`).
- `mt`: `tensao_kv`, `diametro_eletroduto_pol` e `secao_cabo_mm2` (number) obrigatórios; `tipo_cabo`, `temperatura_cabo` e `classe_isolacao` são opcionais e anuláveis.
- `aterramento`: `tipo_sistema` (enum `TN-S`/`TN-C`/`TN-C-S`/`TT`/`IT`), `qtd_hastes` (integer ≥ 1) e `secao_cabo_cobre_mm2` (number > 0), todos obrigatórios. **Sem** `secao_cabo_malha_mm2` e sem `local_bep` (decisão 4).
- `equipamentos`: array com `minItems: 1`. Cada item tem `nome` (string, `minLength: 1`), `potencia` (string ou null, por exemplo `"7,5 CV"`) e `qtd` (integer ≥ 1).
- `quadros`: array com `minItems: 1`. Cada item tem `nome` (string, `minLength: 1`), `carga_w` (number > 0), `carga_formatada` (string, preenchida pelo builder) e `descricao` (string ou null).
- Não existem as seções `gerador`, `nao_inclusos` nem `instalacao`.

**Fixture `eletrico_canteiro_bothanic_expected.json`:** valores reais tirados das plantas V05. Ela é o oráculo das Tasks 4 e 7:
- `obra`: construtora `"MOREIRA & RUFFO'S LTDA"`, nome `"BOTHANIC"`, localização `"R. Manuel Cavalcanti de Souza esq. c/ a Av. Adolfo Loureiro, S/N, Cabo Branco, João Pessoa - PB"`, numero_cadastro `"46/2024"`.
- `energia`: `tem_subestacao: true`, `tipo_subestacao: "subestação aérea abaixadora"`, `potencia_transformador_kva: 75`.
- `aterramento`: `qtd_hastes: 3`, `secao_cabo_cobre_mm2: 50`.
- `quadros`, em ordem de aparição: `Q.G.B.T.` 89088, `Q.D.L/T TORRE` 12714, `Q.D.STAND` 9170, `Q.D.APOIO` 33837, `Q.D.ELEV. CREMALHEIRA` 13800, `Q.D.MÓVEL` 3851.
- `equipamentos`, conforme o rótulo de potência na planta: `Betoneira` `"7,5 CV"`, `Policorte` `"3 CV"`, `Bancada de serra` `"5 CV"`, `Peneira` `"1 CV"`, `Esmeril` `"1/4 CV"`, `Mini guincho` sem potência, `Elevador cremalheira` sem potência; todos com `qtd: 1`.

- [ ] **Step 1: Criar o branch.** `git checkout -b feat/eletrico-canteiro-v1`

- [ ] **Step 2: Escrever os testes que devem falhar**

```python
# tests/test_memorial_validator.py
def test_validate_eletrico_canteiro_accepts_bothanic_fixture(self) -> None:
    context = build_memorial_eletrico_canteiro_v1_context(load_bothanic_fixture())
    validate_memorial_eletrico_canteiro_v1_context(context)  # não levanta

def test_validate_eletrico_canteiro_rejects_building_fields(self) -> None:
    payload = load_bothanic_fixture(); payload["obra"]["qtd_apartamentos"] = 30
    with self.assertRaises(MemorialValidationError):
        validate_memorial_eletrico_canteiro_v1_context(build_memorial_eletrico_canteiro_v1_context(payload))

def test_validate_eletrico_canteiro_rejects_empty_quadros_and_equipamentos(self) -> None:
    # quadros=[] → issue com path "$.quadros"; equipamentos=[] → issue com path "$.equipamentos"

# tests/test_context_builder.py
def test_canteiro_builder_defaults_mt_tensao_to_13_8(self) -> None:
    ctx = build_memorial_eletrico_canteiro_v1_context({"mt": {}})
    self.assertEqual(ctx["mt"]["tensao_kv"], 13.8)

def test_canteiro_builder_keeps_extracted_mt_tensao(self) -> None:
    # {"mt": {"tensao_kv": 13.2}} → 13.2 (default não sobrescreve)

def test_canteiro_builder_formats_quadro_load_and_known_description(self) -> None:
    ctx = build_memorial_eletrico_canteiro_v1_context({"quadros": [{"nome": "Q.G.B.T.", "carga_w": 89088}]})
    self.assertEqual(ctx["quadros"][0]["carga_formatada"], "89.088 W")
    self.assertEqual(ctx["quadros"][0]["descricao"],
        "Concentra todos os demais quadros e equipamentos específicos de maior potência.")

def test_canteiro_builder_unknown_quadro_gets_null_description(self) -> None:
    # {"nome": "Q.D.BOMBAS", "carga_w": 1000} → descricao None
```

- [ ] **Step 3: Rodar e confirmar que falham.** `python -m unittest tests.test_memorial_validator tests.test_context_builder` deve dar ImportError ou falha nos testes novos.

- [ ] **Step 4: Implementar o schema, a fixture, o loader, o validator e o builder**

O builder:
- aplica `setdefault` de `CANTEIRO_DEFAULTS` (tabela acima, mais `mt.tensao_kv = 13.8`), de `documento.data_atual` e das porcentagens (reusar `PORCENTAGEM_ENTRE_TRAFOS` e `PORCENTAGEM_ENTRE_QUADROS` do elétrico);
- quando `tem_subestacao` é false, aplica o mesmo `NULLABLE_ENERGIA_KEYS` do elétrico;
- para cada quadro: `carga_formatada = f"{int(round(carga_w)):,} W".replace(",", ".")` e `descricao` buscada em `QUADRO_DESCRICOES_CONHECIDAS` pela chave normalizada (ASCII, maiúscula, sem pontos nem espaços).

As chaves e os textos de `QUADRO_DESCRICOES_CONHECIDAS` vêm da seção 8 do exemplo:
- `QGBT`: "Concentra todos os demais quadros e equipamentos específicos de maior potência."
- `QDLTTORRE`: "Iluminação e tomadas ao longo dos pavimentos, bem como alguns equipamentos móveis, como vibradores."
- `QDAPOIO`: "Circuitos de luz, TUGs e TUEs de dormitórios, vestiários e refeitórios."
- `QDSTAND`: "Circuitos de luz, TUGs e TUEs do stand de vendas e escritório."
- `QDMOVEL`: "Equipamentos móveis, como guinchos e vibradores."

O `notes.md` documenta as seções condicionais (só `energia.tem_subestacao`) e lista os defaults assumidos.

- [ ] **Step 5: Rodar até passar.** `python -m unittest tests.test_memorial_validator tests.test_context_builder` deve dar OK.

- [ ] **Step 6: Commit.** `git commit -m "feat(canteiro): contrato v1 (schema, validator, context builder)"`

---

### Task 2: Template DOCX, renderer e geração por JSON (gate de render)

**Files:**
- Create: `templates/eletrico_canteiro/v1/template.docx`
- Modify: `app/services/memorial_renderer.py` (junto de `render_memorial_eletrico_v1`, linha 141)
- Modify: `app/services/pipeline.py` (junto de `generate_memorial_eletrico_v1`, linha 40)
- Test: `tests/test_memorial_renderer.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 1 (`build_…`, `validate_…`, fixture).
- Produces:
  - `ELETRICO_CANTEIRO_V1_TEMPLATE_PATH`
  - `render_memorial_eletrico_canteiro_v1(context: dict[str, Any], output_path: Path) -> Path`
  - `generate_memorial_eletrico_canteiro_v1(raw_payload: dict[str, Any], output_path: Path) -> PipelineResult`

**Montagem do template:** partir de uma **cópia** de `templates/eletrico/v1/template.docx` (já formatado e com o Jinja de subestação) e editar no Word ou no LibreOffice, usando como texto-alvo o memorial de exemplo. Diferenças obrigatórias em relação ao elétrico:
- **Título:** "MEMORIAL DESCRITIVO E ESPECIFICAÇÕES TÉCNICAS DAS INSTALAÇÕES ELÉTRICAS-BT DO CANTEIRO DE OBRAS DO {{ obra.nome }}".
- **Introdução:** "…para a completa execução das instalações elétricas do canteiro de obras do empreendimento, conforme abaixo descrito."
- **Dados da obra:** só construtora, obra e localização.
- **Requisitos gerais:** uma frase, "…de acordo com as indicações dos desenhos e deste memorial e conforme o andamento da obra."; sem o parágrafo de "conforme construído".
- **Disposições gerais:** remover os 6 primeiros parágrafos do elétrico (firma instaladora, garantia, CREA, INSS, subempreitada). Manter os demais, como no exemplo.
- **Disposições de base:** remover os parágrafos de fabricantes/NBRs e de projeto luminotécnico.
- **Visão geral:** remover a frase condicional de grupo gerador.
- **Subestação:** o título passa a "SUBESTAÇÃO AÉREA" e a seção "DADOS CONSTRUTIVOS DA SUBESTAÇÃO" sai inteira. O resto continua condicional a `energia.tem_subestacao`.
- **Remover inteiras:** "INSTALAÇÃO DE LUZ ESSENCIAL (GRUPO GERADOR)", "ITENS NÃO INCLUSOS", "Ligações Equipotenciais" e o bloco do BEP, além de "PERFILADO", "SUPORTES PARA PERFILADOS", "ELETROCALHAS", "CONDULETES" e "TOMADAS DE FORÇA – ÁREA EXTERNA" nas especificações.
- **Proteção contra choques:** trocar o parágrafo "Os condutores terra… BEP… SPDA" pelo texto novo da seção "Valores assumidos".
- **Seções novas, com texto fixo do exemplo:** "6. NORMAS CONSIDERADAS NO PROJETO", com os dois parágrafos.
- **Seção nova "7. EQUIPAMENTOS DO CANTEIRO DE OBRAS":** a frase "O canteiro na fase na qual se encontra, apresenta os seguintes equipamentos:" seguida de `{%p for e in equipamentos %}{{ e.nome }}{% if e.potencia %} {{ e.potencia }}{% endif %}: {{ "%02d"|format(e.qtd) }} unidade{% if e.qtd > 1 %}s{% endif %}{%p endfor %}`.
- **Seção nova "8. QUADROS DE DISTRIBUIÇÃO NO CANTEIRO DE OBRAS":** a frase "Os quadros de distribuição previstos no canteiro de obras, conforme projeto, são os seguintes:" seguida de `{%p for q in quadros %}{{ q.nome }} – {{ q.carga_formatada }}{% if q.descricao %}: {{ q.descricao }}{% endif %}{%p endfor %}`.
- **Sumário:** estático, como no elétrico, com o ramo `{%p if energia.tem_subestacao %}…{%p else %}…{%p endif %}`. Seções com subestação: 4.1 a 4.10, 5.1 a 5.4, 6, 7 e 8. Sem subestação, 4.2 some e as seguintes sobem uma posição. O sumário não lista gerador nem itens não inclusos. **Não copiar** os erros do exemplo ("Centro de Convenções de Patos-PB" e números de página trocados).

- [ ] **Step 1: Escrever os testes que devem falhar**

```python
def test_render_canteiro_bothanic_has_no_template_tokens(self) -> None:
    # render da fixture Bothanic; assert_no_jinja_left/markers via render; texto contém
    # "CANTEIRO DE OBRAS DO BOTHANIC", "SUBESTAÇÃO AÉREA", "75 kVA", "MT-13.8kV"
    # (usar o mesmo formato numérico que o template elétrico produz para mt.tensao_kv)

def test_render_canteiro_lists_real_quadros_with_loads(self) -> None:
    # texto contém "Q.G.B.T. – 89.088 W" e "Q.D.MÓVEL – 3.851 W"

def test_render_canteiro_omits_building_and_bep_and_gerador_text(self) -> None:
    for absent in ("Quantidade de apartamentos", "BEP", "GRUPO GERADOR", "ITENS NÃO INCLUSOS",
                   "DADOS CONSTRUTIVOS DA SUBESTAÇÃO", "SPDA", "PERFILADO"):
        self.assertNotIn(absent, text)

def test_render_canteiro_equipment_without_potencia_has_no_placeholder_text(self) -> None:
    # texto contém "Mini guincho: 01 unidade" e não contém "None" nem "()"

def test_render_canteiro_without_subestacao_omits_section_and_renumbers(self) -> None:
    # tem_subestacao=False → sem "SUBESTAÇÃO AÉREA"; sumário contém "4.2. ATERRAMENTO"
    # e não contém "4.10."

# tests/test_pipeline.py
def test_generate_memorial_eletrico_canteiro_v1_writes_docx(self) -> None:
    # PipelineResult.output_path existe; context["mt"]["tensao_kv"] == 13.8 quando omitido
```

- [ ] **Step 2: Rodar e confirmar que falham.** `python -m unittest tests.test_memorial_renderer tests.test_pipeline`

- [ ] **Step 3: Montar o template e implementar o renderer e o pipeline.** O renderer espelha `render_memorial_eletrico_v1`; o pipeline segue `build → validate → render`.

- [ ] **Step 4: Rodar até passar.** Se `assert_no_jinja_left` acusar tag fragmentada entre runs do DOCX, reescrever o placeholder num único run no editor. **Não** contornar no código.

- [ ] **Step 5: Gerar o DOCX da fixture e abrir no Word para conferência visual.** Anexar o arquivo ao PR para o engenheiro revisar.

- [ ] **Step 6: Commit.** `git commit -m "feat(canteiro): template v1 e geração por JSON"`

---

### Task 3: Registro na API, rota JSON, persistência e correção

**Files:**
- Modify: `app/api/routes.py`. São 8 pontos:
  - `_SUPPORTED_MEMORIAL_TYPES` (l.119)
  - `_PROJECT_NAME_BY_TYPE` (l.121)
  - `_TEMPLATE_VERSION_BY_TYPE` (l.398)
  - `_generate_memorial_from_uploaded_files` (l.408)
  - `_generate_memorial_from_context` (l.424)
  - `_validation_detail_for_type` (l.565)
  - a rota nova `POST /api/v1/memoriais/eletrico-canteiro`, no modelo da rota `gas-natural` (l.1063)
  - a rota nova `POST /api/v1/memoriais/eletrico-canteiro/upload`, no modelo da l.1192
- Modify: `app/services/generated_memorial_store.py` (`_FILENAME_BY_TYPE`, l.21)
- Test: `tests/test_api.py`, `tests/test_generated_memorial_api.py`

**Interfaces:**
- Consumes: `generate_memorial_eletrico_canteiro_v1` (Task 2). O dispatcher de upload passa a chamar `generate_memorial_eletrico_canteiro_v1_from_uploaded_files`, que só existe na Task 6. Nesta task, o ramo `"eletrico-canteiro"` de `_generate_memorial_from_uploaded_files` fica para a Task 6, e o teste de persistência usa o mock que os testes de gás já usam.
- Produces: o tipo `eletrico-canteiro` aceito por `/from-files/persist`, pela listagem com filtro de tipo e pela correção de memorial persistido.

- [ ] **Step 1: Escrever os testes que devem falhar**

```python
def test_post_memorial_eletrico_canteiro_returns_docx_for_valid_payload(self) -> None: ...
def test_post_memorial_eletrico_canteiro_returns_400_with_canteiro_message(self) -> None:
    # body["detail"] == "Payload invalido para o memorial eletrico canteiro v1."
def test_list_memorials_accepts_type_eletrico_canteiro(self) -> None: ...
def test_correct_persisted_eletrico_canteiro_memorial_rerenders(self) -> None:
    # PATCH/rota de correção existente com context corrigido → 200 e novo docx
def test_generated_memorial_store_filename_for_eletrico_canteiro(self) -> None:
    # "memorial_eletrico_canteiro_v1.docx"
```

- [ ] **Step 2: Rodar e confirmar que falham.** `python -m unittest tests.test_api tests.test_generated_memorial_api`
- [ ] **Step 3: Implementar os registros e as rotas**, com os valores da seção Global Constraints.
- [ ] **Step 4: Rodar até passar.**
- [ ] **Step 5: Commit.** `git commit -m "feat(canteiro): registra tipo na API, persistência e correção"`

---

### Task 4: Mapper determinístico do canteiro (texto real do Bothanic)

**Files:**
- Create: `tests/fixtures/canteiro_bothanic_planta_text.txt`. É o texto das duas pranchas, gerado com `fitz.open(pdf)[0].get_text()` e as duas concatenadas com `\n`.
- Modify: `app/services/extraction_mapper.py`. As funções novas ficam depois de `map_extraction_to_partial_glp_context`.
- Test: `tests/test_extraction_mapper.py`

**Interfaces:**
- Produces:
  - `map_extraction_to_partial_eletrico_canteiro_context(extraction_result: ProjectExtractionResult) -> MappingResult`
  - `assess_eletrico_canteiro_extraction_coverage(mapping: MappingResult) -> ExtractionReport`
  - `CANTEIRO_EXTRACTABLE_BY_MAPPER: list[str]` = `obra.construtora`, `obra.numero_cadastro`, `energia.tem_subestacao`, `energia.tipo_subestacao`, `energia.potencia_transformador_kva`, `aterramento.qtd_hastes`, `aterramento.secao_cabo_cobre_mm2`, `quadros`
  - `CANTEIRO_PENDING_EXTRACTION: list[str]` = `obra.nome`, `obra.localizacao`, `equipamentos`, que ficam a cargo da LLM

**Regras e evidência.** As regex abaixo rodam sobre `_normalize_text(raw_text)`, com espaços colapsados. Foram conferidas em 16/11 no texto real: 12 ocorrências de quadros deduplicadas em 6 com as cargas exatas, `75` kVA, `3` hastes e cabo `50` mm². Sobre o texto cru, a regra do cabo não casa, por causa das quebras de linha.
- **Reaproveitar** `_extract_construtora` e `_extract_numero_cadastro`. No texto do Bothanic eles já retornam `"MOREIRA & RUFFO'S LTDA"` e `"46/2024"`.
- **Não** usar `_extract_aterramento_tipo_sistema`, porque lê "TT" da legenda (Review Focus 3). O default vem do builder.
- **Subestação:** `SE\s+A[ÉE]REA\s+(\d+(?:[.,]\d+)?)\s*KVA`. O texto da planta traz "SE AÉREA 75KVA". O resultado é `tem_subestacao=True`, `tipo_subestacao="subestação aérea abaixadora"`, `potencia_transformador_kva=75`.
- **Hastes:** `M[ÍI]NIMA:\s*(\d+)\s+HASTES`. O texto traz "# TERRA MÍNIMA: 3 HASTES 5/8"".
- **Cabo da malha:** `#\s*(\d+)\s*mm².{0,40}aterramento`, sem diferenciar maiúsculas. O texto traz "#50mm² Ø32mm Sobe Ø32mm p/ aterramento".
- **Quadros:** `(Q\.G\.B\.T\.|Q\.D\.\s*[A-ZÀ-Ú/][A-ZÀ-Ú/ .]*?)\s*=\s*(\d{1,3}(?:\.\d{3})*(?:,\d+)?)\s*W`. A carga é `int(valor.replace(".", "").split(",")[0])`. Deduplicar pelo nome normalizado, mantendo a primeira ocorrência.

- [ ] **Step 1: Gerar a fixture de texto a partir dos 2 PDFs** e comitá-la junto com o teste.
- [ ] **Step 2: Escrever os testes que devem falhar**

```python
def test_canteiro_mapper_extracts_bothanic_core_fields(self) -> None:
    ctx = map_extraction_to_partial_eletrico_canteiro_context(bothanic_extraction()).context
    self.assertEqual(ctx["obra"]["construtora"], "MOREIRA & RUFFO'S LTDA")
    self.assertEqual(ctx["energia"]["potencia_transformador_kva"], 75)
    self.assertEqual(ctx["aterramento"]["qtd_hastes"], 3)
    self.assertEqual(ctx["aterramento"]["secao_cabo_cobre_mm2"], 50)

def test_canteiro_mapper_dedupes_quadros_repeated_across_sheets(self) -> None:
    self.assertEqual(len(ctx["quadros"]), 6)

def test_canteiro_mapper_parses_brazilian_thousands_in_quadro_loads(self) -> None:
    self.assertEqual({q["nome"]: q["carga_w"] for q in ctx["quadros"]}, {
        "Q.G.B.T.": 89088, "Q.D.L/T TORRE": 12714, "Q.D.STAND": 9170,
        "Q.D.APOIO": 33837, "Q.D.ELEV. CREMALHEIRA": 13800, "Q.D.MÓVEL": 3851})

def test_canteiro_mapper_does_not_infer_tipo_sistema_from_legend(self) -> None:
    self.assertNotIn("tipo_sistema", ctx.get("aterramento", {}))

def test_canteiro_coverage_reports_equipamentos_as_pending(self) -> None: ...
```

`bothanic_extraction()` monta um `ProjectExtractionResult` com `raw_text` igual ao conteúdo da fixture, usando o construtor já usado nos testes de mapper de gás.

- [ ] **Step 3: Rodar e confirmar que falham.** `python -m unittest tests.test_extraction_mapper`
- [ ] **Step 4: Implementar.**
- [ ] **Step 5: Rodar até passar.**
- [ ] **Step 6: Commit.** `git commit -m "feat(canteiro): mapper deterministico a partir das plantas"`

---

### Task 5: Estratégia de LLM do canteiro

**Files:**
- Modify: `app/services/llm_extractor.py`. Os modelos ficam junto dos do elétrico (l.58–124), o prompt depois de `GLP_MERGE_PROMPT` e a estratégia junto de `ELETRICO_STRATEGY` (l.1667).
- Test: `tests/test_llm_extractor.py`

**Interfaces:**
- Consumes: `ObraExtraction` (reusar só `construtora`, `nome`, `localizacao` e `numero_cadastro` num modelo novo), `EnergiaExtraction`, `MTExtraction`, `_run_llm_extraction` e `ExtractionStrategy`.
- Produces:
  - `CanteiroObraExtraction`, `CanteiroAterramentoExtraction` (`qtd_hastes` e `secao_cabo_cobre_mm2`), `EquipamentoExtraction` (`nome`, `potencia`, `qtd`), `QuadroExtraction` (`nome`, `carga_w`) e `EletricoCanteiroLLMExtraction` (`obra`, `energia`, `mt`, `aterramento`, `equipamentos: list[EquipamentoExtraction] = []`, `quadros: list[QuadroExtraction] = []`, `observacoes`)
  - `ELETRICO_CANTEIRO_EXTRACTION_PROMPT` e `ELETRICO_CANTEIRO_MERGE_PROMPT`
  - `ELETRICO_CANTEIRO_STRATEGY`
  - `extract_eletrico_canteiro_with_llm_result(source_files: list[ExtractedSourceFile]) -> LLMExtractionRunResult`, que respeita `is_llm_extraction_enabled()` como a versão de telecom

**Conteúdo do prompt** (em inglês, como os demais). É uma planta de canteiro de obras (instalação provisória):
- obra vem do carimbo (CONSTRUTOR, EDIFÍCIO, LOCAL);
- a subestação vem da indicação "SE AÉREA nnKVA";
- quadros são os diagramas "Q.G.B.T." e "Q.D.*", com a carga total em W de cada um;
- equipamentos são máquinas de obra rotuladas na planta (betoneira, policorte, bancada de serra, peneira, esmeril, guincho/mini guincho, elevador cremalheira, grua, vibrador, bombas). Usar a potência exatamente como rotulada (ex.: "7,5 CV") e contar uma unidade por símbolo na planta;
- **nunca** extrair apartamentos, lojas, BEP ou gerador;
- ignorar a legenda de símbolos.

- [ ] **Step 1: Escrever os testes que devem falhar**, no mesmo estilo dos de gás (sem rede, com o cliente mockado):

```python
def test_canteiro_llm_schema_defaults_are_empty(self) -> None:
    m = EletricoCanteiroLLMExtraction()
    self.assertEqual(m.quadros, []); self.assertEqual(m.equipamentos, [])
    self.assertIsNone(m.obra.nome)

def test_canteiro_llm_schema_has_no_building_fields(self) -> None:
    self.assertNotIn("qtd_apartamentos", CanteiroObraExtraction.model_fields)

def test_extract_eletrico_canteiro_returns_empty_when_disabled(self) -> None: ...
def test_extract_eletrico_canteiro_uses_canteiro_strategy(self) -> None:
    # mock _run_llm_extraction → chamado com ELETRICO_CANTEIRO_STRATEGY
```

- [ ] **Step 2: Rodar e confirmar que falham.** `python -m unittest tests.test_llm_extractor`
- [ ] **Step 3: Implementar.** As funções de extração por arquivo e de merge seguem `_extract_telecom_single_file` e `_merge_telecom_with_llm`.
- [ ] **Step 4: Rodar até passar.**
- [ ] **Step 5: Commit.** `git commit -m "feat(canteiro): estrategia de extracao LLM"`

---

### Task 6: Pipeline a partir de arquivos e rota from-files

**Files:**
- Modify: `app/services/pipeline_from_files.py`. As funções novas ficam depois de `extract_telecom_mapping_from_ingested_files` (l.795).
- Modify: `app/api/routes.py`, com o ramo `"eletrico-canteiro"` em `_generate_memorial_from_uploaded_files` e a rota `POST /api/v1/memoriais/eletrico-canteiro/from-files` no modelo da elétrica (l.1249).
- Test: `tests/test_pipeline_from_files.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: Tasks 1, 2, 4 e 5.
- Produces:
  - `extract_eletrico_canteiro_mapping_from_ingested_files(files: list[IngestedFileMetadata]) -> tuple[MappingResult, ExtractionReport]`
  - `generate_memorial_eletrico_canteiro_v1_from_ingested_files(files, output_path) -> PipelineResult`
  - `async generate_memorial_eletrico_canteiro_v1_from_uploaded_files(files, output_path) -> PipelineResult`

**Fluxo:** igual ao telecom. Com LLM ligada, a LLM é a fonte principal e o mapper preenche só o que ficou `None` (`_fill_gaps`). As **listas** `quadros` e `equipamentos` são tratadas como valor único: a do mapper só entra quando a da LLM vier vazia. **Não** chamar `_apply_schematic_apartment_count_override`, porque o canteiro não tem apartamentos. Erro de validação é reempacotado com `extraction_report`, como no elétrico (l.953).

- [ ] **Step 1: Escrever os testes que devem falhar**

```python
def test_canteiro_from_files_mapper_only_fails_with_equipamentos_issue(self) -> None:
    # USE_LLM_EXTRACTION desligado + fixture de texto → MemorialValidationError com issue
    # path "$.equipamentos" e extraction_report presente
def test_canteiro_from_files_llm_quadros_win_over_mapper(self) -> None:
    # LLM mock retorna 2 quadros → contexto final tem os 2 da LLM, não os 6 do mapper
def test_canteiro_from_files_mapper_quadros_fill_when_llm_empty(self) -> None:
    # LLM mock retorna quadros=[] → contexto final tem os 6 do mapper
def test_post_eletrico_canteiro_from_files_returns_docx(self) -> None: ...
def test_post_eletrico_canteiro_from_files_persist_creates_record(self) -> None:
    # /api/v1/memoriais/eletrico-canteiro/from-files/persist → 201, memorial_type "eletrico-canteiro"
```

- [ ] **Step 2: Rodar e confirmar que falham.** `python -m unittest tests.test_pipeline_from_files tests.test_api`
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar até passar.**
- [ ] **Step 5: Commit.** `git commit -m "feat(canteiro): geracao a partir de arquivos"`

---

### Task 7: Aceite com as plantas reais e regressão completa

**Files:**
- Create: `projects/canteiro/01_CANTEIRO OBRA BOTHANIC_V05.pdf` e `02_…` (mesmo critério de `projects/eletrico/`). Antes de comitar, confirmar com a TecPred que as plantas podem entrar no repositório.
- Create: `scripts/acceptance_canteiro_bothanic.py`

**Interfaces:**
- Consumes: `generate_memorial_eletrico_canteiro_v1_from_uploaded_files` e a fixture `eletrico_canteiro_bothanic_expected.json`.

- [ ] **Step 1: Escrever o script de aceite.** Ele roda o pipeline real (OpenAI ligada, `OPENAI_MODEL` do ambiente) nos 2 PDFs e compara com a fixture esperada:
  - `obra.construtora`, `energia.potencia_transformador_kva`, `aterramento.qtd_hastes` e os 6 quadros com a carga exata;
  - cada equipamento esperado presente pelo nome (casamento sem diferenciar maiúsculas);
  - `mt.tensao_kv == 13.8`.

  O script imprime as divergências campo a campo e sai com código diferente de zero se houver alguma.
- [ ] **Step 2: Rodar.** `APP_ENV=local USE_LLM_EXTRACTION=true python scripts/acceptance_canteiro_bothanic.py`. O esperado é o DOCX gerado e zero divergências. Se houver divergência, ajustar o prompt (Task 5) ou o mapper (Task 4) com um teste novo que fixe o caso, e não o oráculo.
- [ ] **Step 3: Regressão completa.** `python -m unittest discover -s tests` deve passar com todos os 411 testes anteriores e os novos.
- [ ] **Step 4: Abrir o DOCX gerado no Word** e anexá-lo ao PR para o engenheiro validar texto e layout.
- [ ] **Step 5: Commit e PR.** `git commit -m "test(canteiro): aceite com plantas Bothanic"`. No PR, listar a tabela "Valores assumidos" para o engenheiro confirmar.

## Fora do escopo

- **Dashboard (repo externo):** card ou opção de categoria "Elétrico — Canteiro de Obras" chamando `POST /api/v1/memoriais/eletrico-canteiro/from-files/persist`. Avisar o responsável pelo frontend.
- Fluxo de review-session para o canteiro.
- Corrigir o falso positivo "TT" no mapper do **elétrico** (`_extract_aterramento_tipo_sistema` lendo a legenda). Registrar como issue separada.
