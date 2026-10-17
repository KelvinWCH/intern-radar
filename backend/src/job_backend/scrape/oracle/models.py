from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, JsonValue


@dataclass(frozen=True)
class OracleSite:
    host: str
    # path under /sites/ in the public url
    site: str
    # internal site number the search api wants, like cx_1
    site_number: str


@dataclass
class OracleListingBudget:
    malformed: int = 0


class OracleFacet(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    Id: int | None = None
    Name: str | None = None
    TotalCount: int | None = None


class OracleSearchPage(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    TotalJobsCount: int = Field(ge=0)
    requisitionList: list[dict[str, JsonValue]] = Field(default_factory=list[dict[str, JsonValue]])
    locationsFacet: list[OracleFacet] = Field(default_factory=list[OracleFacet])


class OracleSearch(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    items: list[OracleSearchPage] = Field(min_length=1, max_length=1)


class OracleRequisition(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    Id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")


class OracleDetail(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    Id: str = Field(min_length=1)
    Title: str = Field(min_length=1)
    ExternalDescriptionStr: str | None = None
    ExternalResponsibilitiesStr: str | None = None
    ExternalQualificationsStr: str | None = None
    ShortDescriptionStr: str | None = None

    def has_description(self) -> bool:
        return any(
            text and text.strip()
            for text in (
                self.ExternalDescriptionStr,
                self.ExternalResponsibilitiesStr,
                self.ExternalQualificationsStr,
                self.ShortDescriptionStr,
            )
        )


class OracleDetails(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    items: list[dict[str, JsonValue]]


class OracleRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    listing: dict[str, JsonValue]
    detail: dict[str, JsonValue] | None = None
