import base64
import hashlib
import hmac
import secrets

from job_backend.auth.constants import (
    HASH_BYTES,
    SALT_BYTES,
    SCRYPT_MAX_MEMORY,
    SCRYPT_N,
    SCRYPT_P,
    SCRYPT_R,
)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAX_MEMORY,
        dklen=HASH_BYTES,
    )
    return f"scrypt:{SCRYPT_N}:{SCRYPT_R}:{SCRYPT_P}:{_encode(salt)}:{_encode(digest)}"


def check_hash_format(encoded: str) -> None:
    parts = encoded.split(":")
    try:
        if len(parts) != 6 or parts[0] != "scrypt":
            raise ValueError
        n, r, p = (int(part) for part in parts[1:4])
        if n < 2**14 or n & (n - 1) or not 0 < r <= 32 or not 0 < p <= 16:
            raise ValueError
        if 128 * r * (n + p + 2) > SCRYPT_MAX_MEMORY:
            raise ValueError
        if len(_decode(parts[4])) < SALT_BYTES or len(_decode(parts[5])) != HASH_BYTES:
            raise ValueError
    except ValueError:
        raise ValueError(
            "JOB_AUTH_PASSWORD_HASH must come from python -m job_backend.auth.hash_password"
        ) from None


def verify_password(password: str, encoded: str) -> bool:
    _, n, r, p, salt, expected = encoded.split(":")
    digest = hashlib.scrypt(
        password.encode(),
        salt=_decode(salt),
        n=int(n),
        r=int(r),
        p=int(p),
        maxmem=SCRYPT_MAX_MEMORY,
        dklen=HASH_BYTES,
    )
    return hmac.compare_digest(digest, _decode(expected))
