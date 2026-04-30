#!/usr/bin/env python3

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRD_PATH = ROOT / "prd.json"
LEARNINGS_PATH = ROOT / "learnings.md"
STATE_PATH = ROOT / ".ralph_state.json"
LAST_MESSAGE_PATH = ROOT / ".ralph_last_message.md"
PROMPT_PATH = ROOT / ".ralph_prompt.md"


def load_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def read_text(path, default=""):
    if not path.exists():
        return default

    return path.read_text(encoding="utf-8")


def write_text(path, content):
    path.write_text(content, encoding="utf-8")


def append_text(path, content):
    with path.open("a", encoding="utf-8") as file:
        file.write(content)


def run(command, *, input_text=None, timeout_seconds=None):
    print("")
    print("$ " + " ".join(command))

    return subprocess.run(
        command,
        cwd=ROOT,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=timeout_seconds
    )


def ensure_git_repo():
    result = run(["git", "rev-parse", "--is-inside-work-tree"])

    if result.returncode != 0 or result.stdout.strip() != "true":
        print("ERRO: este diretório não parece ser um repositório Git.")
        sys.exit(1)


def ensure_required_files():
    missing = []

    for path in [PRD_PATH, LEARNINGS_PATH, ROOT / "verify.py"]:
        if not path.exists():
            missing.append(path.name)

    if missing:
        print("ERRO: arquivos obrigatórios ausentes:")
        for name in missing:
            print(f"- {name}")
        sys.exit(1)


def load_state():
    if not STATE_PATH.exists():
        return {"completed_story_ids": []}

    return load_json(STATE_PATH)


def save_state(state):
    write_text(STATE_PATH, json.dumps(state, indent=2, ensure_ascii=False))


def build_prompt(prd, story, attempt_number, verify_failure=None):
    learnings = read_text(LEARNINGS_PATH, "")

    prompt = f"""
Você está trabalhando no repositório frontend dashboard-memorial.

Você deve implementar exatamente UMA user story do PRD, com mudanças pequenas, seguras e revisáveis.

PRD completo:
{json.dumps(prd, indent=2, ensure_ascii=False)}

User story atual:
{json.dumps(story, indent=2, ensure_ascii=False)}

Tentativa atual:
{attempt_number}

Learnings acumulados:
{learnings}

Regras obrigatórias:
1. Trabalhe somente neste repositório.
2. Não altere o backend.
3. Não altere contratos de API sem necessidade explícita.
4. Não commite nada.
5. Não adicione dependências novas sem justificar.
6. Preserve funcionalidades existentes.
7. Faça uma implementação incremental e revisável.
8. Ao final, rode os comandos de verificação disponíveis, especialmente build, lint, typecheck e testes se existirem.
9. Depois da implementação, explique resumidamente o que mudou, arquivos alterados, riscos restantes e como revisar manualmente.
"""

    if verify_failure:
        prompt += f"""

A tentativa anterior falhou no verificador com a seguinte saída. Corrija a causa antes de fazer qualquer outro ajuste:

{verify_failure}
"""

    return prompt.strip() + "\n"


def run_codex(prompt):
    write_text(PROMPT_PATH, prompt)

    command = [
        "codex",
        "exec",
        "--full-auto",
        "--output-last-message",
        str(LAST_MESSAGE_PATH),
        prompt
    ]

    result = run(command, timeout_seconds=1800)

    if result.stdout:
        print("")
        print("STDOUT DO CODEX:")
        print(result.stdout)

    if result.stderr:
        print("")
        print("STDERR DO CODEX:")
        print(result.stderr)

    return result.returncode == 0


def run_verify():
    result = run([sys.executable, "verify.py"], timeout_seconds=900)

    output_parts = []

    if result.stdout:
        output_parts.append("STDOUT:\n" + result.stdout)

    if result.stderr:
        output_parts.append("STDERR:\n" + result.stderr)

    output = "\n\n".join(output_parts)

    if output:
        print("")
        print(output)

    return result.returncode == 0, output


def main():
    ensure_git_repo()
    ensure_required_files()

    prd = load_json(PRD_PATH)
    state = load_state()

    completed_story_ids = set(state.get("completed_story_ids", []))
    stories = prd.get("user_stories", [])
    max_iterations = int(prd.get("max_iterations_per_story", 3))

    pending_stories = [
        story for story in stories
        if story.get("id") not in completed_story_ids
    ]

    if not pending_stories:
        print("Nenhuma user story pendente.")
        return

    story = pending_stories[0]
    story_id = story.get("id", "unknown-story")

    print(f"Rodando Ralph para a story: {story_id} - {story.get('title', '')}")

    verify_failure = None

    for attempt_number in range(1, max_iterations + 1):
        print("")
        print(f"===== Tentativa {attempt_number}/{max_iterations} =====")

        prompt = build_prompt(
            prd=prd,
            story=story,
            attempt_number=attempt_number,
            verify_failure=verify_failure
        )

        codex_ok = run_codex(prompt)

        if not codex_ok:
            verify_failure = "O Codex retornou erro antes do verify.py."
            append_text(
                LEARNINGS_PATH,
                f"\n\n## Falha na story {story_id}, tentativa {attempt_number}\n\n{verify_failure}\n"
            )
            continue

        verify_ok, verify_output = run_verify()

        if verify_ok:
            print("")
            print(f"Story {story_id} concluída com sucesso.")

            state.setdefault("completed_story_ids", []).append(story_id)
            save_state(state)

            append_text(
                LEARNINGS_PATH,
                f"\n\n## Story {story_id} concluída\n\nTentativa bem-sucedida: {attempt_number}\n"
            )

            return

        verify_failure = verify_output or "verify.py falhou sem saída."

        append_text(
            LEARNINGS_PATH,
            f"\n\n## Falha na story {story_id}, tentativa {attempt_number}\n\n{verify_failure}\n"
        )

    print("")
    print(f"ERRO: Story {story_id} não passou após {max_iterations} tentativas.")
    print("Revise o git diff, a saída do verify.py e o arquivo learnings.md.")
    sys.exit(1)


if __name__ == "__main__":
    main()
