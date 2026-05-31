from pathlib import Path

from dotenv import load_dotenv


def load_environment() -> None:
    current = Path.cwd()
    for path in (current / ".env", current / "backend" / ".env"):
        if path.is_file():
            load_dotenv(path, override=False)
            return
