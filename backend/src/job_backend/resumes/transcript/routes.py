from fastapi import APIRouter, HTTPException, Response, UploadFile

from job_backend.persistence.database import Database
from job_backend.resumes.transcript.constants import MAX_TRANSCRIPT_BYTES
from job_backend.resumes.transcript.models import TranscriptInfo
from job_backend.resumes.transcript.storage import (
    TranscriptError,
    delete_transcript,
    save_transcript,
    transcript_filename,
    transcript_info,
    transcript_pdf,
)


def create_router(engine: Database) -> APIRouter:
    router = APIRouter()

    @router.get("/transcript", summary="Describe the saved transcript, or null")
    def get_transcript() -> TranscriptInfo | None:
        return transcript_info(engine)

    @router.put("/transcript", summary="Upload or replace the transcript PDF")
    def put_transcript(file: UploadFile) -> TranscriptInfo:
        content = file.file.read(MAX_TRANSCRIPT_BYTES + 1)
        try:
            return save_transcript(engine, file.filename or "", content)
        except TranscriptError as error:
            status = 413 if len(content) > MAX_TRANSCRIPT_BYTES else 422
            raise HTTPException(status_code=status, detail=str(error)) from None

    @router.delete("/transcript", status_code=204, summary="Remove the saved transcript")
    def remove_transcript() -> Response:
        delete_transcript(engine)
        return Response(status_code=204)

    @router.get(
        "/transcript/pdf",
        response_class=Response,
        responses={200: {"content": {"application/pdf": {}}}},
        summary="Download the saved transcript",
    )
    def download_transcript() -> Response:
        content = transcript_pdf(engine)
        if content is None:
            raise HTTPException(status_code=404, detail="No transcript uploaded")
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{transcript_filename(engine)}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    return router
