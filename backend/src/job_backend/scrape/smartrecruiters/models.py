from pydantic import BaseModel, ConfigDict, Field, JsonValue


class SmartRecruitersListing(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1)


class SmartRecruitersPage(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    totalFound: int = Field(ge=0)
    content: list[dict[str, JsonValue]]


class SmartRecruitersPosting(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    jobAd: dict[str, JsonValue]
    postingUrl: str | None = None
    applyUrl: str | None = None


class SmartRecruitersRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    listing: dict[str, JsonValue]
    detail: dict[str, JsonValue]
