from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue, TypeAdapter, field_validator


@dataclass(frozen=True)
class WorkdayBoard:
    api_url: str
    careers_url: str


@dataclass
class WorkdayListingBudget:
    pages: int = 0
    bytes: int = 0
    malformed: int = 0
    repeated: int = 0
    missing: int = 0
    facets: JsonValue = None
    scope: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])


class WorkdayFacetValue(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    id: str = Field(min_length=1)
    count: int = Field(ge=0)


class WorkdayFacet(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    facetParameter: str = Field(min_length=1)
    values: list[WorkdayFacetValue]


class WorkdayListing(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    title: str | None = Field(default=None, min_length=1)
    externalPath: str = Field(min_length=1)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Workday title must not be blank")
        return value

    @field_validator("externalPath")
    @classmethod
    def validate_external_path(cls, value: str) -> str:
        if (
            not value.startswith("/job/")
            or any(character in value for character in ("?", "#", "\\", "%"))
            or any(segment in {"", ".", ".."} for segment in value[1:].split("/"))
        ):
            raise ValueError("Workday externalPath must be an unambiguous /job/ path")
        return value


class WorkdayListingPage(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    total: int = Field(ge=0)
    jobPostings: list[dict[str, JsonValue]]


class WorkdayPostingInfo(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    jobDescription: str = Field(min_length=1)
    jobReqId: str = Field(min_length=1)
    externalUrl: str | None = None

    @field_validator("id", "title", "jobDescription", "jobReqId")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Workday posting fields must not be blank")
        return value

    @field_validator("externalUrl")
    @classmethod
    def validate_external_url(cls, value: str | None) -> str | None:
        if value is not None:
            TypeAdapter(HttpUrl).validate_python(value)
        return value


class WorkdayPostingDetail(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    jobPostingInfo: WorkdayPostingInfo


class WorkdayRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    listing: dict[str, JsonValue]
    detail: dict[str, JsonValue] | None = None
    student_facet: str | None = None
