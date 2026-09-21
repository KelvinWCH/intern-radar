from dataclasses import dataclass
from typing import ClassVar

from job_backend.common.models import StrictModel
from job_backend.persistence.models import StoredRecord


@dataclass(kw_only=True)
class TranscriptRecord(StoredRecord):
    collection: ClassVar[str] = "user_transcript"
    key_fields: ClassVar[tuple[str, ...]] = ("id",)
    id: int = 1
    filename: str = ""
    content: str = ""
    size: int = 0
    page_count: int = 0
    uploaded_at: int = 0


class TranscriptInfo(StrictModel):
    filename: str
    size: int
    page_count: int
    uploaded_at: int
