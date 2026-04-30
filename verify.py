import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(command: list[str], *, allow_missing: bool = False) -> None:
    print(f"\n$ {' '.join(command)}")
    try:
        result = subprocess.run(command, cwd=ROOT, check=False)
    except FileNotFoundError:
        if allow_missing:
            print(f"SKIP: command not found: {command[0]}")
            return
        raise

    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("APP_ENV", "test")

    run([sys.executable, "-m", "compileall", "app", "tests"])

    if (ROOT / "pyproject.toml").exists():
        run([sys.executable, "-m", "ruff", "check", "."], allow_missing=True)

    run([sys.executable, "-m", "pytest"])


if __name__ == "__main__":
    main()
