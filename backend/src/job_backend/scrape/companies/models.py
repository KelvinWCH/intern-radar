import re
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, HttpUrl, TypeAdapter, field_validator, model_validator

from job_backend.common.models import StrictModel

_BOARD_NAME = r"^[a-zA-Z0-9_.-]+$"
_ASHBY_BOARD_NAME = r"^[a-zA-Z0-9_.-]+(?: [a-zA-Z0-9_.-]+)*$"


class Company(StrictModel):
    key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    careers_url: str
    job_board: Literal[
        "lever",
        "greenhouse",
        "ashby",
        "workday",
        "workable",
        "hibob",
        "employmenthero",
        "smartrecruiters",
        "successfactors",
        "avature",
        "recruitee",
        "oracle",
        "other",
    ]
    board_name: str | None = None
    region: Literal["global", "eu"] = "global"
    notes: str | None = None

    @field_validator("careers_url")
    @classmethod
    def validate_careers_url(cls, value: str) -> str:
        return str(TypeAdapter(HttpUrl).validate_python(value))

    @model_validator(mode="after")
    def validate_board(self) -> Self:
        if self.job_board == "other":
            if self.board_name is not None:
                raise ValueError("Other careers sites must not advertise a supported board name")
        elif self.board_name is None:
            raise ValueError("Supported company APIs require a board_name")
        elif not re.fullmatch(
            _ASHBY_BOARD_NAME if self.job_board == "ashby" else _BOARD_NAME, self.board_name
        ):
            raise ValueError("board_name contains characters the provider does not use")
        if self.job_board == "workday":
            parts = urlsplit(self.careers_url)
            if (
                parts.scheme != "https"
                or not re.fullmatch(r"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com", parts.hostname or "")
                or parts.username is not None
                or parts.password is not None
                or parts.port not in {None, 443}
                or parts.query
                or parts.fragment
                or parts.path.rstrip("/").rsplit("/", 1)[-1] != self.board_name
            ):
                raise ValueError("Workday requires its public tenant URL and matching site name")
        if self.job_board in {"successfactors", "avature", "recruitee"}:
            parts = urlsplit(self.careers_url)
            path = parts.path.strip("/")
            host = parts.hostname or ""
            if (
                parts.scheme != "https"
                or "." not in host
                or parts.username is not None
                or parts.password is not None
                or parts.port not in {None, 443}
                or parts.query
                or parts.fragment
            ):
                raise ValueError("Career sites require a public HTTPS address")
            if self.job_board == "successfactors" and host != self.board_name:
                raise ValueError("SuccessFactors board_name must be the career site's host")
            if self.job_board == "avature" and path != self.board_name:
                raise ValueError("Avature careers_url must end at its portal, the board_name")
            if self.job_board == "recruitee" and host != f"{self.board_name}.recruitee.com":
                raise ValueError("Recruitee careers_url must be the board's recruitee.com site")
        if self.job_board == "oracle":
            parts = urlsplit(self.careers_url)
            if (
                parts.scheme != "https"
                or not re.fullmatch(
                    r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.oraclecloud\.com", parts.hostname or ""
                )
                or not re.fullmatch(
                    r"/hcmUI/CandidateExperience/[a-z]{2}(?:-[A-Za-z]{2})?/sites/[A-Za-z0-9_-]+/?",
                    parts.path,
                )
                or parts.query
                or parts.fragment
            ):
                raise ValueError(
                    "Oracle requires its public candidate-experience site URL; board_name is "
                    "the site number"
                )
        if self.region == "eu" and self.job_board != "lever":
            raise ValueError("The EU endpoint setting applies only to Lever")
        return self

    @property
    def supports_scraping(self) -> bool:
        return self.job_board in {
            "lever",
            "greenhouse",
            "ashby",
            "workday",
            "workable",
            "hibob",
            "employmenthero",
            "smartrecruiters",
            "successfactors",
            "avature",
            "recruitee",
            "oracle",
        }

    @property
    def source_name(self) -> str:
        if not self.supports_scraping:
            raise ValueError(f"{self.name} needs a dedicated careers-page adapter")
        if self.job_board == "workday":
            tenant = (urlsplit(self.careers_url).hostname or "").split(".")[0]
            return f"workday-{tenant}-{self.board_name}"
        if self.job_board == "avature":
            return f"avature-{urlsplit(self.careers_url).hostname}-{self.board_name}"
        if self.job_board == "oracle":
            host = (urlsplit(self.careers_url).hostname or "").split(".")[0]
            return f"oracle-{host}-{self.board_name}"
        region = "-eu" if self.region == "eu" else ""
        return f"{self.job_board}{region}-{(self.board_name or '').replace(' ', '-')}"
