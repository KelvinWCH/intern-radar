import base64
import time
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.resumes.filenames import document_filename
from job_backend.resumes.storage import ResumeNotFoundError, load_resume
from job_backend.resumes.transcript.constants import (
    MAX_TRANSCRIPT_BYTES,
    MAX_TRANSCRIPT_PAGES,
)
from job_backend.resumes.transcript.models import TranscriptInfo, TranscriptRecord


class TranscriptError(ValueError):
    pass


def save_transcript(engine: Database, filename: str, content: bytes) -> TranscriptInfo:
    if len(content) > MAX_TRANSCRIPT_BYTES:
        raise TranscriptError("Transcript exceeds 5 MiB")
    if not content.startswith(b"%PDF-"):
        raise TranscriptError("Upload the transcript as a PDF")
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise TranscriptError("Upload an unencrypted PDF")
        pages = len(reader.pages)
    except PyPdfError:
        raise TranscriptError("Could not read this PDF; export it again and retry") from None
    if not 0 < pages <= MAX_TRANSCRIPT_PAGES:
        raise TranscriptError(f"Transcript must have 1 to {MAX_TRANSCRIPT_PAGES} pages")
    record = TranscriptRecord(
        filename=filename.strip()[:200] or "transcript.pdf",
        content=base64.b64encode(content).decode("ascii"),
        size=len(content),
        page_count=pages,
        uploaded_at=int(time.time()),
    )
    with Session(engine) as session, session.begin():
        session.merge(record)
    return _info(record)


def transcript_info(engine: Database) -> TranscriptInfo | None:
    record = _load(engine)
    return _info(record) if record else None


def transcript_pdf(engine: Database) -> bytes | None:
    record = _load(engine)
    return base64.b64decode(record.content) if record else None


def transcript_filename(engine: Database) -> str:
    try:
        applicant = load_resume(engine).name
    except ResumeNotFoundError:
        applicant = ""
    return document_filename("", applicant, "transcript", "pdf")


def delete_transcript(engine: Database) -> None:
    with Session(engine) as session, session.begin():
        record = session.get(TranscriptRecord, 1)
        if record is not None:
            session.delete(record)


def _load(engine: Database) -> TranscriptRecord | None:
    with Session(engine) as session:
        return session.get(TranscriptRecord, 1)


def _info(record: TranscriptRecord) -> TranscriptInfo:
    return TranscriptInfo(
        filename=record.filename,
        size=record.size,
        page_count=record.page_count,
        uploaded_at=record.uploaded_at,
    )
