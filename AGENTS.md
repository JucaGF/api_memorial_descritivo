# AGENTS.md

Este arquivo define como agentes de código devem trabalhar neste repositório.

Leia este arquivo antes de modificar qualquer código.

---

# Objetivo do projeto

Este projeto implementa um sistema para geração automática de memoriais descritivos de engenharia a partir de projetos técnicos.

O sistema recebe arquivos de projeto (PDF ou DOCX), extrai informações relevantes e gera um memorial descritivo DOCX utilizando templates.

O sistema está sendo desenvolvido começando pelo **memorial elétrico v1**.

---

# Princípios de arquitetura

O sistema deve ser construído seguindo estes princípios:

1. Separação clara de responsabilidades
2. Pipeline determinístico para geração de memoriais
3. Validação forte de dados antes da renderização
4. Template DOCX como fonte de verdade do documento
5. Código modular e testável

Evite criar arquiteturas genéricas ou abstrações complexas antes de serem necessárias.

---

# Pipeline esperado do sistema

A primeira versão funcional do sistema deve implementar o pipeline completo:

1. Upload de arquivos de projeto
2. Armazenamento temporário dos arquivos
3. Extração de dados relevantes dos documentos
4. Construção do contexto estruturado do memorial
5. Validação do contexto contra o schema do template
6. Renderização do template DOCX
7. Retorno do memorial final

O foco inicial é **memorial elétrico v1**.

Não implemente suporte a múltiplos tipos de memorial nesta etapa.

---

# Estrutura esperada do código

O projeto deve evoluir para uma estrutura semelhante a:

```

app/
api/
core/
schemas/
services/
file_ingestion.py
project_extractor.py
context_builder.py
memorial_validator.py
memorial_renderer.py
main.py

```

Cada serviço deve ter responsabilidade única.

---

# Template e schema

O template do memorial elétrico está localizado em:

```

templates/eletrico/v1/template.docx

```

O schema de validação está em:

```

templates/eletrico/v1/schema.json

```

O schema define o contrato de dados necessário para renderizar o template.

Sempre valide os dados contra o schema antes de renderizar.

---

# Renderização do template

A renderização utiliza **docxtpl**.

Regras importantes:

- O documento final não pode conter placeholders Jinja.
- Não deixar tags `{% %}` ou `{{ }}` no documento final.
- O template deve ser renderizado apenas com dados validados.

A renderização do template deve ser **determinística**.

Não utilize LLM para gerar partes do documento final.

---

# Extração de dados

A extração de dados dos projetos pode utilizar:

- parsing de PDF
- parsing de DOCX
- LLM
- visão computacional

Mas a saída dessa etapa deve sempre ser convertida em um **contexto estruturado compatível com o schema**.

---

# Testes

Testes existentes:

```

scripts/test_render_eletrico.py

```

Esse script valida:

- renderização do template
- ausência de placeholders
- cenários com e sem subestação

Novos serviços devem ser testáveis isoladamente.

---

# Regras para modificar código

Antes de modificar código:

1. Leia o README.md
2. Leia este AGENTS.md
3. Inspecione a estrutura do projeto

Evite:

- modificar muitos arquivos em uma única mudança
- criar abstrações desnecessárias
- modificar templates sem atualizar o schema
- remover validações existentes

---

# Definition of Done

Uma tarefa só está completa quando:

- o código implementa a funcionalidade solicitada
- o código é consistente com a arquitetura do projeto
- os testes relevantes passam
- nenhuma regra deste AGENTS.md foi violada
- o código é legível e modular

---

# Restrições importantes

Não:

- remover validação de schema
- usar LLM para gerar o memorial final
- alterar o template sem justificativa
- criar dependência externa desnecessária
- modificar arquivos fora do repositório

---

# Primeira meta de desenvolvimento

Implementar a primeira versão funcional do pipeline completo para o memorial elétrico v1.

Essa versão deve incluir:

- endpoint de API
- upload de arquivos
- extração inicial de dados
- construção do contexto do template
- validação contra schema
- geração do DOCX final
```
