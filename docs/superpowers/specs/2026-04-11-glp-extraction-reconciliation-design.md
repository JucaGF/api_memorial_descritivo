# GLP Extraction Reconciliation Design

## Goal

Make the GLP file-based memorial pipeline produce canonical, deterministic data before validation and rendering by improving extraction source priority, normalization, reconciliation, and conflict reporting.

## Scope

In scope:
- GLP file-based extraction
- GLP mapping and normalization
- deterministic reconciliation rules
- extraction conflict reporting
- targeted GLP tests

Out of scope:
- DOCX template wording changes
- render-layer phrase cleanup
- schema redesign outside the current GLP contract

## Current Problem

The current GLP pipeline can generate a DOCX, but key fields are still unreliable:
- `ramal.primario_diametro` may arrive in inches and needs canonical millimeters
- `ramal.primario_pavimento` and `teto_ou_piso` need better normalization
- `soma.qtd_pontos_de_utilizacao` can diverge from project quantitative tables
- appliance totals can diverge from project totals
- cross-sheet contradictions are not surfaced as structured conflicts

The core gap is not missing extraction alone. It is the absence of deterministic field-family reconciliation after LLM extraction.

## Proposed Architecture

The GLP file pipeline remains LLM-first, but post-LLM processing becomes stricter:

1. Run required GLP LLM extraction.
2. Run deterministic GLP mapper extraction from OCR text for fields that benefit from explicit rules.
3. Normalize canonical values:
   - convert inch notation to millimeters
   - normalize `teto_ou_piso`
   - normalize `ramal.primario_pavimento`
4. Reconcile field families using explicit source-priority rules:
   - quantitative tables win for totals when parseable
   - deterministic table sums win over isolated single values
   - cut/schematic sheets win for ramal fields when parseable
5. If a conflict is resolved by a deterministic rule, continue and record it.
6. If a conflict cannot be resolved deterministically, fail before render with a structured report.

## Field-Family Rules

### Ramal

- `ramal.primario_diametro`
  - accept mm or inch notation
  - normalize to millimeters
- `ramal.primario_material`
  - prefer deterministic evidence from cut/detail text when present
- `ramal.primario_pavimento`
  - normalize to canonical location tokens such as `subsolo`, `térreo`
- `teto_ou_piso`
  - normalize to canonical tokens such as `teto`, `piso`, `contrapiso`, `enterrado`

### Totals

- `soma.qtd_pontos_de_utilizacao`
  - prefer deterministic sum from quantitative tables
  - otherwise fall back to LLM extraction
- `dimensionamento.qtd_fogao`
- `dimensionamento.qtd_aquecedor`
- `dimensionamento.qtd_churrasqueira`
  - prefer deterministic quantitative evidence where available
  - otherwise keep LLM value

### Sheet/Conflict Reporting

- `numero.prancha`
  - prefer schematic/cut sheet identifiers when parseable
- cross-sheet contradictions
  - record the observed values and the rule used
  - fail if no deterministic rule resolves the conflict

## Affected Files

- `app/services/pipeline_from_files.py`
- `app/services/extraction_mapper.py`
- `app/services/llm_extractor.py`
- `tests/test_pipeline_from_files.py`
- `tests/test_api.py`
- `tests/test_llm_extractor.py`

## Verification

- targeted GLP pipeline tests
- targeted GLP API tests
- targeted GLP LLM extractor tests
- real `projects/gas-glp` API generation smoke test after code changes
