import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    backend = root / "backend"
    python = backend / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not python.is_file() or npm is None or not (root / "frontend/node_modules").is_dir():
        print("Install backend .venv dev dependencies and run npm ci in frontend to check locally.")
        return 1
    commands = [
        (root / "frontend", [npm, "run", "check"]),
        (
            backend,
            [str(python), "-m", "ruff", "check", "--config", "pyproject.toml", ".", "../scripts"],
        ),
        (
            backend,
            [
                str(python),
                "-m",
                "ruff",
                "format",
                "--check",
                "--config",
                "pyproject.toml",
                ".",
                "../scripts",
            ],
        ),
        (root, [str(python), "-m", "pyright"]),
        (backend, [str(python), "-m", "pytest"]),
    ]
    with tempfile.TemporaryDirectory(prefix="intern-radar-check-") as check_temp:
        for directory, command in commands:
            if command[-1] == "pytest":
                command.extend(
                    [
                        "--basetemp",
                        str(Path(check_temp) / "pytest"),
                        "-o",
                        f"cache_dir={Path(check_temp) / 'cache'}",
                    ]
                )
            print(f"\nChecking {directory.name}: {' '.join(command[1:])}", flush=True)
            result = subprocess.run(command, cwd=directory, check=False)
            if result.returncode:
                print("Quality check failed: fix the reported issue and try again.", flush=True)
                return result.returncode
    print("All quality checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
