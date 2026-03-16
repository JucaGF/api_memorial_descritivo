# API Memorial Descritivo

Sistema para geração automática de memoriais descritivos de engenharia a partir de projetos técnicos (PDF/DOCX).

O sistema recebe arquivos de projeto, extrai informações relevantes e gera automaticamente um memorial descritivo estruturado com base em templates DOCX.

---

# Objetivo do projeto

Automatizar a criação de memoriais descritivos utilizados em projetos de engenharia.

Fluxo geral esperado do sistema:

1. Upload de arquivos de projeto (PDF ou DOCX)
2. Extração automática de informações relevantes
3. Construção do contexto estruturado do memorial
4. Validação do contexto contra o schema do template
5. Geração do memorial DOCX
6. Revisão humana opcional
7. Armazenamento do memorial

---

# Estado atual do projeto

O template do **memorial elétrico v1** já foi preparado e validado.

Arquivos principais:

```

templates/eletrico/v1/template.docx
templates/eletrico/v1/schema.json
templates/eletrico/v1/notes.md

```

O template utiliza **docxtpl** com sintaxe Jinja2 para renderização condicional.

Também existem fixtures de teste para validar a renderização:

```

tests/fixtures/

```

E um script de teste de renderização:

```

scripts/test_render_eletrico.py

```

Esse script garante que:

- o template renderiza corretamente
- não restam placeholders Jinja no documento final
- os cenários com e sem subestação funcionam corretamente

---

# Estrutura atual do repositório

```

templates/
eletrico/
v1/
template.docx
schema.json
notes.md

tests/
fixtures/
output/

scripts/
test_render_eletrico.py

.codex/
config.toml

AGENTS.md
README.md

```

---

# Próxima etapa de desenvolvimento

A próxima etapa é implementar a **primeira versão funcional do sistema completo**.

Essa versão inicial será focada apenas no **memorial elétrico v1**, mas já implementará o pipeline real do sistema.

Pipeline planejado:

1. API recebe arquivos de projeto
2. Arquivos são armazenados temporariamente
3. Sistema extrai dados relevantes dos documentos
4. Dados extraídos são convertidos para o contexto do template
5. Contexto é validado contra o schema
6. Template DOCX é renderizado
7. Memorial final é retornado ao usuário

---

# Tecnologias utilizadas

- Python
- FastAPI
- docxtpl
- python-docx
- jsonschema
- Supabase
- pytest
- ruff

---

# Regras importantes do sistema

- O **template DOCX é a fonte de verdade do memorial**.
- O **schema JSON define o contrato de dados do template**.
- A renderização do template deve ser **determinística (sem uso de LLM)**.
- A extração de dados dos projetos pode utilizar LLM ou visão computacional.
- A geração final do memorial **não pode depender de LLM**.

---

# Execução de testes atuais

Para rodar o teste de renderização do template:

```

python scripts/test_render_eletrico.py

```

Os arquivos gerados são salvos em:

```

tests/output/

```

---

# Observações

Este README descreve o estado atual do projeto.

A arquitetura completa do sistema será construída progressivamente a partir da primeira versão funcional do pipeline do memorial elétrico.
```
