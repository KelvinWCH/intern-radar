from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from job_backend.auth.constants import OPEN_PATHS, OPEN_PREFIXES
from job_backend.auth.sessions import Authenticator


def is_open_path(path: str) -> bool:
    return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)


def bearer_token(scope: Scope) -> str | None:
    for name, value in scope["headers"]:
        if name == b"authorization":
            scheme, _, token = value.decode("latin-1").partition(" ")
            return token.strip() if scheme.lower() == "bearer" else None
    return None


class RequireSession:
    def __init__(self, app: ASGIApp, authenticator: Authenticator) -> None:
        self.app = app
        self.authenticator = authenticator

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] == "OPTIONS"
            or is_open_path(scope["path"])
            or self.authenticator.accepts(bearer_token(scope))
        ):
            await self.app(scope, receive, send)
            return
        response = JSONResponse(
            {"detail": "Sign in to use this backend.", "code": "sign_in_required"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)
