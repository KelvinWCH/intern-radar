from fastapi import APIRouter

from job_backend.resumes.compile_pdf.http import validated_pdf
from job_backend.resumes.models import GeneratedCoverLetter
from job_backend.resumes.render_cover_letter.models import LatexCoverLetter
from job_backend.resumes.render_cover_letter.render import cover_letter_to_latex

router = APIRouter()


@router.post("/cover-letter/latex", summary="Convert a generated cover letter to LaTeX")
def render_latex(letter: GeneratedCoverLetter) -> LatexCoverLetter:
    source = cover_letter_to_latex(letter)
    validated_pdf(source)
    return LatexCoverLetter(latex=source)
