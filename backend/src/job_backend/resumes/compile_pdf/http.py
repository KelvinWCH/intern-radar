from fastapi import HTTPException

from job_backend.resumes.compile_pdf.compile import (
    DocumentLayoutError,
    PdfCompilerError,
    compile_one_page,
)


def validated_pdf(source: str) -> bytes:
    try:
        return compile_one_page(source)
    except DocumentLayoutError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except PdfCompilerError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
