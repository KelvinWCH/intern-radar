from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from job_backend.resumes.upload_resume.constants import MAX_UPLOAD_BYTES
from job_backend.resumes.upload_resume.documents import ResumeUploadError, extract_resume_text


@pytest.mark.parametrize("extension", ["txt", "md", "tex"])
def test_reads_text_and_latex(extension: str) -> None:
    source = "Alex Example\nPython & Redis\n" + r"\input{not-a-real-file}"
    assert extract_resume_text(f"resume.{extension}", source.encode(), max_chars=1000) == source


def test_pdf_upload_extracts_actual_text() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 700 Td (Alex Example - Python) Tj ET")
    page[NameObject("/Contents")] = stream
    buffer = BytesIO()
    writer.write(buffer)
    assert "Alex Example - Python" in extract_resume_text(
        "resume.pdf", buffer.getvalue(), max_chars=1000
    )


@pytest.mark.parametrize(
    ("name", "content", "limit"),
    [
        ("resume.exe", b"text", 100),
        ("resume.txt", b"x" * (MAX_UPLOAD_BYTES + 1), 100),
        ("resume.pdf", b"not a PDF", 100),
    ],
    ids=["extension", "empty", "blank"],
)
def test_invalid_files(name: str, content: bytes, limit: int) -> None:
    with pytest.raises(ResumeUploadError):
        extract_resume_text(name, content, max_chars=limit)
