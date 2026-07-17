from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class EmploymentHeroPosting(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    title: str = Field(min_length=1)
    application_url: str
    vendor_location_name: str | None = None
    created_at: str | None = None
    eoi: bool = False

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("EmploymentHero job title must not be blank")
        return value

    @field_validator("application_url")
    @classmethod
    def validate_application_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or parts.hostname not in {"jobs.employmenthero.com", "employmenthero.com"}
            or parts.username is not None
            or parts.password is not None
            or parts.port not in {None, 443}
            or "/jobs/" not in parts.path
        ):
            raise ValueError("EmploymentHero requires a public job description URL")
        return value


class EmploymentHeroPage(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    items: list[dict[str, JsonValue]]
    item_per_page: int = Field(ge=1)
    page_index: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    total_items: int = Field(ge=0)


class EmploymentHeroResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    data: EmploymentHeroPage
