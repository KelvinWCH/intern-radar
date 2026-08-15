from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, TypeAdapter, field_validator


class WorkablePosting(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    shortcode: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    url: str
    application_url: str | None = None

    @field_validator("shortcode", "title", "description")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Workable posting fields must not be blank")
        return value

    @field_validator("url", "application_url")
    @classmethod
    def validate_job_url(cls, value: str | None) -> str | None:
        if value is not None:
            TypeAdapter(HttpUrl).validate_python(value)
        return value


class WorkableFeed(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    name: str = Field(min_length=1)
    jobs: list[dict[str, JsonValue]]
