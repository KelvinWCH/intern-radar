from dataclasses import dataclass, field
from typing import ClassVar, Literal

from pydantic import Field

from job_backend.common.models import StrictModel
from job_backend.persistence.models import StoredRecord

MatchBand = Literal["strong", "good", "fair", "low"]


@dataclass(kw_only=True)
class JobEmbedding(StoredRecord):
    collection: ClassVar[str] = "job_embeddings"
    key_fields: ClassVar[tuple[str, ...]] = ("job_id",)
    job_id: str = ""
    model: str = ""
    content_hash: str = ""
    vector: str = ""
    title_vector: str = ""
    described: bool = True
    text: str = ""
    graduation_years: list[int] = field(default_factory=list[int])
    embedded_at: int = 0


@dataclass(kw_only=True)
class JobMatch(StoredRecord):
    collection: ClassVar[str] = "job_matches"
    key_fields: ClassVar[tuple[str, ...]] = ("job_id",)
    job_id: str = ""
    content_hash: str = ""
    score: int = 0
    band: MatchBand = "low"
    reasons: list[str] = field(default_factory=list[str])
    skills: list[str] = field(default_factory=list[str])
    role: str | None = None
    components: dict[str, float] = field(default_factory=dict[str, float])
    scored_at: int = 0


@dataclass(kw_only=True)
class MatchState(StoredRecord):
    collection: ClassVar[str] = "match_state"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: str = "current"
    state_key: str = ""
    model: str = ""
    device: str = ""
    profile_revision: int = 0
    positives: list[str] = field(default_factory=list[str])
    negatives: list[str] = field(default_factory=list[str])
    role_queries: list[str] = field(default_factory=list[str])
    role_vectors: list[str] = field(default_factory=list[str])
    background_vector: str = ""
    positive_vector: str | None = None
    negative_vector: str | None = None
    calibration: dict[str, list[float]] = field(default_factory=dict[str, list[float]])
    skill_idf: dict[str, float] = field(default_factory=dict[str, float])
    total: int = 0
    calibrated_jobs: int = 0
    embedded: int = 0
    scored: int = 0
    bands: dict[str, int] = field(default_factory=dict[str, int])
    updated_at: int = 0
    error: str | None = None


class JobMatchView(StrictModel):
    score: int = Field(ge=0, le=100)
    band: MatchBand
    reasons: list[str] = Field(description="Short readable reasons, strongest first.")
    skills: list[str] = Field(description="Profile skills the posting names, rarest first.")
    role: str | None = Field(description="The closest of the profile's target roles.")
    components: dict[str, float] = Field(
        description="Calibrated parts of the score between 0 and 1: role, background, skills, "
        "location, feedback, student, and eligibility."
    )
    scored_at: int = Field(ge=0)


class MatchStatus(StrictModel):
    model: str | None
    device: str | None
    total: int = Field(ge=0, description="Saved jobs that can be scored.")
    embedded: int = Field(ge=0)
    scored: int = Field(ge=0)
    bands: dict[str, int]
    profile_revision: int = Field(ge=0)
    positives: int = Field(ge=0, description="Saved, applied, added, or tailored jobs used.")
    negatives: int = Field(ge=0, description="Deleted or withdrawn jobs used.")
    updated_at: int | None
    error: str | None
