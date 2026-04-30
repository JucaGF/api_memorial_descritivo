import os
import shutil
import subprocess
import sys


def run(command: list[str], required: bool = True) -> bool:
    print(f"\n$ {' '.join(command)}")
    result = subprocess.run(command)
    if result.returncode != 0 and required:
        raise SystemExit(result.returncode)
    return result.returncode == 0


def has_file(*paths: str) -> bool:
    return any(os.path.exists(path) for path in paths)


def main() -> None:
    run([sys.executable, "-m", "pytest"])

    if shutil.which("ruff"):
        run(["ruff", "check", "."], required=False)

    if has_file("mypy.ini", "pyproject.toml") and shutil.which("mypy"):
        run(["mypy", "."], required=False)

    if shutil.which("python"):
        run([sys.executable, "-c", "import app.main"], required=True)


if __name__ == "__main__":
    main()
