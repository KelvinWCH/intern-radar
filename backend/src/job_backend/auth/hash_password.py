import getpass
import sys

from job_backend.auth.constants import (
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    PASSWORD_HASH_ENV,
)
from job_backend.auth.passwords import hash_password


def main() -> int:
    password = getpass.getpass("New sign-in password: ")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        print(f"Use at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Type it again: ") != password:
        print("The passwords differ; nothing was printed.", file=sys.stderr)
        return 1
    print(f"{PASSWORD_HASH_ENV}={hash_password(password)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
