from fastapi import APIRouter
from fastapi.responses import JSONResponse

from job_backend.auth.models import SessionResponse, SignInRequest
from job_backend.auth.sessions import Authenticator, SignInPausedError, WrongPasswordError


def create_router(authenticator: Authenticator) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/auth/session",
        summary="Sign in with the deployment's password",
        response_model=SessionResponse,
    )
    def sign_in(request: SignInRequest) -> SessionResponse | JSONResponse:
        try:
            token, expires_at = authenticator.sign_in(request.password)
        except WrongPasswordError:
            return JSONResponse(
                status_code=401,
                content={"detail": "That password is not right.", "code": "wrong_password"},
            )
        except SignInPausedError as error:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many wrong passwords. Try again in a minute.",
                    "code": "sign_in_paused",
                },
                headers={"Retry-After": str(error.retry_after)},
            )
        return SessionResponse(token=token, expires_at=expires_at)

    return router
