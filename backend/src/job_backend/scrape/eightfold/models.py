from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


@dataclass(frozen=True)
class EightfoldBoard:
    origin: str
    domain: str


class EightfoldEnvelope(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    status: int = Field(ge=200, le=200)
    data: dict[str, JsonValue]
    error: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("error")
    @classmethod
    def validate_error(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        if value.get("message") or value.get("body"):
            raise ValueError("Eightfold response contains an API error")
        return value


class EightfoldListingPage(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    count: int = Field(ge=0)
    positions: list[dict[str, JsonValue]]


class EightfoldPosition(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    id: int = Field(gt=0)
    name: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Eightfold position name must not be blank")
        return value


class EightfoldDetail(EightfoldPosition):
    jobDescription: str = Field(min_length=1)

    @field_validator("jobDescription")
    @classmethod
    def validate_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Eightfold description must not be blank")
        return value


class EightfoldRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    listing: dict[str, JsonValue]
    detail: dict[str, JsonValue]
