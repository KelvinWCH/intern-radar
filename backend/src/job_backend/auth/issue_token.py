import sys

from job_backend.auth.sessions import Authenticator

TOKEN_SECONDS = 60 * 60


def main() -> int:
    authenticator = Authenticator.from_environment()
    if authenticator is None:
        print("JOB_AUTH_PASSWORD_HASH is not set; this backend needs no token.", file=sys.stderr)
        return 1
    print(authenticator.issue(TOKEN_SECONDS)[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
