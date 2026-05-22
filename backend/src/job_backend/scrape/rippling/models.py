from pydantic import BaseModel, ConfigDict, Field


class RipplingDescription(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    company: str | None = None
    role: str = Field(min_length=1)


class RipplingPageJob(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    uuid: str = Field(min_length=1)
    name: str = Field(min_length=1)
    companyName: str | None = None
    description: RipplingDescription
    workLocations: list[str] = Field(default_factory=list)
    url: str
