Perfeito. Como esse arquivo é para o agente, o ideal é que ele seja **bem operacional**, com:

- quando usar
- estrutura obrigatória
- como atualizar progresso
- como registrar decisões
- critérios de conclusão

Abaixo está uma versão de `PLANS.md` já alinhada com o seu repositório e com o uso no Codex:

````markdown
# PLANS.md

Execution-plan guide for code agents working in this repository.

Use this file when a task is too large, risky, or stateful to be handled safely as a single implicit change.

A plan is required when the task involves one or more of the following:

- changes across multiple modules
- behavior changes in API + services + tests
- medium or high risk of regression
- refactors that may affect existing flows
- changes that require multiple checkpoints
- work that will likely take more than one focused implementation pass
- tasks where preserving behavior is as important as adding behavior

For small and localized changes, a separate plan is not required.

---

# Purpose of a plan

A plan exists to make complex work explicit, reviewable, and easy to resume.

A good plan should answer:

- what is being changed
- why the change is needed
- what must not break
- how the work will be split
- how progress will be tracked
- how success will be verified

The plan is not a brainstorming document.
It is an execution document.

---

# Where to place plans

Default location:

```text
docs/plans/
```
````

If that directory does not exist yet, it may be created.

Suggested filename format:

```text
docs/plans/YYYY-MM-DD-short-task-name.md
```

Example:

```text
docs/plans/2026-03-27-review-session-contract-typing.md
```

Only create a new plan when the task is truly large enough to need one.
Otherwise, keep the task in normal agent workflow.

---

# Rules for working with a plan

When using a plan:

1. Read `README.md`
2. Read `AGENTS.md`
3. Inspect the current code before writing the plan
4. Ground the plan in the current repository state
5. Keep the plan concrete and implementation-oriented
6. Update the plan as milestones are completed
7. Record important discoveries and deviations
8. Do not silently drift away from the approved scope

A plan should reflect reality.
If the code reveals something unexpected, update the plan.

---

# Plan structure

Every plan should contain the sections below.

## 1. Title

A short, precise title describing the task.

Example:

```text
# Review-session contract typing
```

## 2. Goal

Explain the intended outcome in 2 to 6 lines.

This section should describe the target behavior, not the implementation details.

## 3. Why this change is needed

Describe the problem being solved.

Include:

- current limitation
- risk or pain point
- why this work matters now

## 4. Scope

State clearly what is in scope and what is out of scope.

Use two subsections:

- In scope
- Out of scope

This prevents accidental expansion.

## 5. Current state

Describe the relevant current behavior based on the actual code.

Mention:

- key modules
- relevant routes
- stores/services involved
- current tests
- current limitations

This section must be based on repository inspection, not assumptions.

## 6. Constraints to preserve

List the behaviors, contracts, and architectural rules that must remain true.

Examples:

- preserve current API payloads
- keep filesystem and Supabase behavior aligned
- do not remove schema validation
- do not change template behavior
- keep final generation deterministic

## 7. Milestones

Break the work into small checkpoints.

Each milestone should be small enough to verify independently.

Good milestone characteristics:

- focused
- testable
- concrete
- ordered

Example structure:

```text
## Milestones

1. Inspect current contract and dependencies
2. Introduce typed model for extraction_report
3. Adapt session store serialization if needed
4. Update API tests and schema tests
5. Run targeted tests and full regression suite
```

## 8. Detailed implementation notes

For each milestone, describe the likely files and intended approach.

Keep this practical.
Avoid vague language.

Good examples:

- update `app/schemas/review_session.py`
- keep API field names unchanged
- add conversion layer only if required
- prefer typed wrapper over deep refactor

## 9. Risks and watchpoints

Document known risks before implementation.

Examples:

- breaking stored session payload compatibility
- changing external API unexpectedly
- introducing divergence between filesystem and Supabase
- weakening tests by over-mocking
- creating hidden cleanup regressions

## 10. Test plan

List exactly how the work will be verified.

Include:

- targeted tests
- broader regression tests
- any manual verification steps if needed

Examples:

```bash
python -m unittest tests.test_api
python -m unittest tests.test_session_store
python -m unittest tests.test_supabase_session_store
python -m unittest discover -s tests
```

If a task changes mapping, pipelines, or rendering, include those tests too.

## 11. Definition of done

Define observable completion criteria.

A plan is complete only when:

- requested behavior is implemented
- preserved constraints still hold
- relevant tests pass
- the code remains readable
- the plan status is updated

## 12. Progress log

Keep a running log of meaningful progress.

Use short dated entries.

Example:

```text
## Progress log

- 2026-03-27 10:15: inspected current review-session schema and API usage
- 2026-03-27 10:42: identified extraction_report as stable enough for explicit model
- 2026-03-27 11:05: implemented typed schema and adjusted API tests
```

## 13. Final outcome

At the end of the task, add a concise summary:

- what changed
- what did not change
- tests run
- remaining follow-ups, if any

---

# Execution style

Plans should be written in a style that supports direct execution.

Prefer:

- explicit filenames
- explicit behaviors
- small milestones
- observable completion criteria

Avoid:

- vague strategy language
- architecture essays
- large speculative redesigns
- generic future ideas unrelated to the task

This is an execution artifact, not a product vision document.

---

# How agents should use a plan

Recommended sequence:

1. Inspect current code
2. Write the initial plan
3. Validate that the plan matches the current repository state
4. Execute one milestone at a time
5. Update progress after each meaningful milestone
6. Run tests as milestones complete
7. Record any deviation from the original approach
8. Finish by updating the final outcome section

For risky changes, do not implement the entire plan blindly in one pass.
Use milestone-by-milestone execution.

---

# When to revise a plan

Revise the plan if:

- the codebase differs from what was expected
- a milestone reveals hidden coupling
- the chosen approach creates unnecessary breakage
- scope must be reduced to preserve safety
- an implementation detail turns out to be invalid

When revising:

- keep the original goal
- update milestones and risks
- note the reason in the progress log

Do not silently change direction.

---

# Plan review checklist

Before executing a plan, verify:

- the goal is clear
- the scope is bounded
- the current state is grounded in code
- constraints to preserve are explicit
- milestones are small and testable
- the test plan is concrete
- the done criteria are observable

If these are missing, the plan is not ready.

---

# Plan template

Use this template for new plans.

````markdown
# <Task title>

## Goal

<2 to 6 lines describing intended outcome>

## Why this change is needed

- <problem>
- <risk or limitation>
- <why now>

## Scope

### In scope

- <item>
- <item>

### Out of scope

- <item>
- <item>

## Current state

- <relevant route/service/store/module>
- <current behavior>
- <current limitation>
- <existing tests>

## Constraints to preserve

- <constraint>
- <constraint>
- <constraint>

## Milestones

1. <milestone>
2. <milestone>
3. <milestone>

## Detailed implementation notes

### Milestone 1

- Files:
  - `<path>`
  - `<path>`
- Intended change:
  - <change>
  - <change>

### Milestone 2

- Files:
  - `<path>`
- Intended change:
  - <change>

## Risks and watchpoints

- <risk>
- <risk>
- <risk>

## Test plan

### Targeted tests

```bash
<command>
<command>
```
````

### Regression tests

```bash
<command>
```

### Manual verification

- <step>
- <step>

## Definition of done

- <criterion>
- <criterion>
- <criterion>

## Progress log

- <timestamp>: <progress entry>

## Final outcome

- Changed:
  - <item>

- Not changed:
  - <item>

- Tests run:
  - `<command>`

- Follow-ups:
  - <item>

```

---

# Repository-specific guidance

For this repository, plans are especially useful when changing:

- review-session contracts
- session persistence behavior
- filesystem and Supabase consistency
- file-ingestion lifecycle and cleanup
- extraction mapper behavior
- file-based generation pipeline internals
- API behavior that touches existing flows
- template/schema interactions with code changes

For these areas, prefer a plan before implementation.

---

# Final rule

If the task is complex enough that you would otherwise need a long prompt to keep everything straight, write a plan first.
```

Se quiser, no próximo passo eu também posso te entregar um **primeiro plano real já preenchido**, por exemplo para a tarefa de tipagem do `review_session`.
