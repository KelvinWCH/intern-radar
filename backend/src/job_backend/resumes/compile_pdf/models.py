import os
from dataclasses import dataclass
from typing import Protocol

from pydantic import Field

from job_backend.common.environment import load_environment
from job_backend.common.models import StrictModel


@dataclass(frozen=True)
class CompiledPdf:
    pdf: bytes
    log: str


class PdfCompiler(Protocol):
    def __call__(self, source: str, /) -> CompiledPdf: ...


class PdfSettings(StrictModel):
    executable: str = Field(default="tectonic", min_length=1)
    timeout_seconds: float = Field(default=120.0, gt=0, le=600)

    @classmethod
    def from_environment(cls) -> "PdfSettings":
        load_environment()
        return cls(
            executable=os.environ.get("JOB_LATEX_EXECUTABLE") or "tectonic",
            timeout_seconds=float(os.environ.get("JOB_LATEX_TIMEOUT_SECONDS", "120")),
        )
