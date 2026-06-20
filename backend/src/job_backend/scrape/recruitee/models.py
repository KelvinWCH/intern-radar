from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, TypeAdapter, field_validator


class RecruiteeOffer(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    id: int = Field(gt=0)
    title: str = Field(min_length=1, pattern=r"\S")
    careers_url: str
    careers_apply_url: str | None = None

    @field_validator("careers_url", "careers_apply_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str | None:
        if value is not None:
            TypeAdapter(HttpUrl).validate_python(value)
        return value


class RecruiteeFeed(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    offers: list[dict[str, JsonValue]]
