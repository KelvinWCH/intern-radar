from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from job_backend.scrape.hibob.constants import POSTING_ID_PATTERN


class HiBobFeed(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    filterGroups: dict[str, JsonValue]
    jobAdDetails: list[dict[str, JsonValue]]


class HiBobPosting(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    id: str = Field(pattern=POSTING_ID_PATTERN)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    requirements: str | None = None
    responsibilities: str | None = None
    benefits: str | None = None
    site: str | None = None
    country: str | None = None
    publishedAt: str | None = None

    @field_validator("title", "description")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("HiBob title and full description must not be blank")
        return value
