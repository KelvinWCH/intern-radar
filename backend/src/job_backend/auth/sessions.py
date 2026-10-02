import base64
import hashlib
import hmac
import os
import secrets
import time
from collections.abc import Callable
from threading import Lock

from job_backend.auth.constants import (
    FAILURES_BEFORE_PAUSE,
    PASSWORD_HASH_ENV,
    PAUSE_SECONDS,
    SESSION_SECONDS,
)
from job_backend.auth.passwords import check_hash_format, verify_password


class WrongPasswordError(Exception):
    pass


class SignInPausedError(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Sign-in is paused for {retry_after} seconds")
        self.retry_after = retry_after


class Authenticator:
    def __init__(self, password_hash: str, *, clock: Callable[[], float] = time.time) -> None:
        check_hash_format(password_hash)
        self._hash = password_hash
        self._key = hashlib.sha256(b"intern-radar session v1\0" + password_hash.encode()).digest()
        self._clock = clock
        # one check at a time so parallel guesses cant skip the lockout
        self._lock = Lock()
        self._failures = 0
        self._paused_until = 0.0

    @classmethod
    def from_environment(cls) -> "Authenticator | None":
        value = os.environ.get(PASSWORD_HASH_ENV, "").strip()
        return cls(value) if value else None

    def issue(self, lifetime: int = SESSION_SECONDS) -> tuple[str, int]:
        expires = int(self._clock()) + lifetime
        payload = f"{expires}.{secrets.token_urlsafe(16)}"
        return f"{payload}.{self._sign(payload)}", expires

    def accepts(self, token: str | None) -> bool:
        if not token or token.count(".") != 2:
            return False
        payload, signature = token.rsplit(".", 1)
        expires = payload.split(".", 1)[0]
        if not expires.isdigit() or int(expires) <= self._clock():
            return False
        return hmac.compare_digest(signature, self._sign(payload))

    def sign_in(self, password: str) -> tuple[str, int]:
        with self._lock:
            now = self._clock()
            if now < self._paused_until:
                raise SignInPausedError(max(1, round(self._paused_until - now)))
            if not verify_password(password, self._hash):
                self._failures += 1
                if self._failures >= FAILURES_BEFORE_PAUSE:
                    self._paused_until = self._clock() + PAUSE_SECONDS
                raise WrongPasswordError
            self._failures = 0
            return self.issue()

    def _sign(self, payload: str) -> str:
        digest = hmac.new(self._key, payload.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")
