from fastapi import APIRouter, Response

from job_backend.resumes.compile_pdf.http import validated_pdf
from job_backend.resumes.filenames import document_filename
from job_backend.resumes.generation import document_to_latex
from job_backend.resumes.models import GeneratedCoverLetter, GeneratedResume

router = APIRouter()


@router.post(
    "/pdf", summary="Compile a resume and require exactly one page", response_class=Response
)
def resume_pdf(resume: GeneratedResume) -> Response:
    return Response(
        content=validated_pdf(document_to_latex(resume)),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="resume.pdf"', "X-Page-Count": "1"},
    )


@router.post(
    "/cover-letter/pdf",
    summary="Compile a cover letter and require exactly one page",
    response_class=Response,
)
def cover_letter_pdf(letter: GeneratedCoverLetter) -> Response:
    return Response(
        content=validated_pdf(document_to_latex(letter)),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="'
            + document_filename(letter.company, letter.name, "cover-letter", "pdf")
            + '"',
            "X-Page-Count": "1",
        },
    )
