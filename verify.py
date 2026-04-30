import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(command: list[str]) -> None:
    print(f"\n$ {' '.join(command)}")
    result = subprocess.run(command, cwd=ROOT, env={**os.environ, "CI": "true"}, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def detect_package_manager() -> str:
    if (ROOT / "pnpm-lock.yaml").exists() and shutil.which("pnpm"):
        return "pnpm"
    if (ROOT / "yarn.lock").exists() and shutil.which("yarn"):
        return "yarn"
    if shutil.which("npm"):
        return "npm"
    raise SystemExit("No supported package manager found: npm, pnpm, or yarn")


def script_exists(package_json: dict, script_name: str) -> bool:
    return script_name in package_json.get("scripts", {})


def run_script(pm: str, script: str) -> None:
    if pm == "npm":
        run(["npm", "run", script])
    elif pm == "pnpm":
        run(["pnpm", "run", script])
    elif pm == "yarn":
        run(["yarn", script])


def main() -> None:
    package_path = ROOT / "package.json"
    if not package_path.exists():
        raise SystemExit("package.json not found")

    package_json = json.loads(package_path.read_text())
    pm = detect_package_manager()

    for script in ["lint", "typecheck", "test", "build"]:
        if script_exists(package_json, script):
            run_script(pm, script)
        else:
            print(f"\nSKIP: package.json has no script named {script!r}")


if __name__ == "__main__":
    main()
