from pydantic import Field

from job_backend.auth.constants import MAX_PASSWORD_LENGTH
from job_backend.common.models import StrictModel


class SignInRequest(StrictModel):
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class SessionResponse(StrictModel):
    token: str
    expires_at: int = Field(description="Unix seconds when the token stops working.")
