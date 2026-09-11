from fastapi import APIRouter

from job_backend.resumes.compile_pdf.http import validated_pdf
from job_backend.resumes.models import GeneratedResume
from job_backend.resumes.render_latex.models import LatexResume
from job_backend.resumes.render_latex.render import resume_to_latex

router = APIRouter()


@router.post("/latex", summary="Convert a generated resume object to LaTeX")
def render_latex(resume: GeneratedResume) -> LatexResume:
    source = resume_to_latex(resume)
    validated_pdf(source)
    return LatexResume(latex=source)
