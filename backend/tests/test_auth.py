from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from job_backend.auth.constants import FAILURES_BEFORE_PAUSE, PAUSE_SECONDS
from job_backend.auth.passwords import hash_password, verify_password
from job_backend.auth.sessions import Authenticator, SignInPausedError, WrongPasswordError
from job_backend.main import create_app

PASSWORD = "correct horse battery"
ORIGIN = "http://localhost:4200"


@pytest.fixture(scope="module")
def stored_hash() -> str:
    return hash_password(PASSWORD)


@pytest.fixture
def client(tmp_path: Path, monkeypatch: MonkeyPatch, stored_hash: str) -> TestClient:
    monkeypatch.setenv("JOB_AUTH_PASSWORD_HASH", stored_hash)
    return TestClient(create_app(tmp_path / "postgres"))


def test_passwords_are_salted_and_checked(stored_hash: str) -> None:
    assert verify_password(PASSWORD, stored_hash)
    assert not verify_password(PASSWORD + "!", stored_hash)
    assert hash_password(PASSWORD) != stored_hash
    assert "$" not in stored_hash and stored_hash.startswith("scrypt:32768:8:1:")


def test_token_expiry(stored_hash: str) -> None:
    now = [1_000_000.0]
    authenticator = Authenticator(stored_hash, clock=lambda: now[0])
    token, expires = authenticator.issue(lifetime=60)
    assert expires == 1_000_060 and authenticator.accepts(token)
    payload, signature = token.rsplit(".", 1)
    later = str(expires + 3600) + payload[len(str(expires)) :]
    assert not authenticator.accepts(f"{later}.{signature}")
    assert not authenticator.accepts(token[:-1] + ("A" if token[-1] != "A" else "B"))
    assert not Authenticator(hash_password(PASSWORD)).accepts(token)
    for malformed in (None, "", "abc", "1.2", "x.y.z", "1.2.3.4"):
        assert not authenticator.accepts(malformed)
    now[0] = expires
    assert not authenticator.accepts(token)


def test_wrong_password_lockout(stored_hash: str) -> None:
    now = [1_000_000.0]
    authenticator = Authenticator(stored_hash, clock=lambda: now[0])
    for _ in range(FAILURES_BEFORE_PAUSE):
        with pytest.raises(WrongPasswordError):
            authenticator.sign_in("wrong password")
    with pytest.raises(SignInPausedError) as paused:
        authenticator.sign_in(PASSWORD)
    assert paused.value.retry_after == PAUSE_SECONDS
    now[0] += PAUSE_SECONDS
    token, _ = authenticator.sign_in(PASSWORD)
    assert authenticator.accepts(token)
    with pytest.raises(WrongPasswordError):
        authenticator.sign_in("wrong password")
    authenticator.sign_in(PASSWORD)


def test_routes_need_session(client: TestClient) -> None:
    blocked = client.get("/jobs", headers={"Origin": ORIGIN})
    assert blocked.status_code == 401
    assert blocked.json()["code"] == "sign_in_required"
    assert blocked.headers["access-control-allow-origin"] == ORIGIN
    assert client.get("/openapi.json").status_code == 401
    assert client.get("/health").status_code == 200
    preflight = client.options(
        "/jobs",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert preflight.status_code == 200

    wrong = client.post("/auth/session", json={"password": "not it"})
    assert wrong.status_code == 401 and wrong.json()["code"] == "wrong_password"
    signed_in = client.post("/auth/session", json={"password": PASSWORD})
    assert signed_in.status_code == 200
    token = signed_in.json()["token"]
    assert client.get("/jobs", headers={"Authorization": f"Bearer {token}"}).status_code != 401
    assert client.get("/jobs", headers={"Authorization": f"bearer {token}"}).status_code != 401
    assert client.get("/jobs", headers={"Authorization": f"Basic {token}"}).status_code == 401


def test_sign_in_is_off_without_a_password(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "postgres"))
    assert client.get("/jobs").status_code != 401
    assert client.post("/auth/session", json={"password": PASSWORD}).status_code not in (200, 401)
