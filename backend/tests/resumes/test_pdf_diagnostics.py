import hashlib

from job_backend.jobs.models import TailoringJob
from job_backend.resumes.compile_pdf.diagnostics import diagnose_pdf, normalize_pdf_text
from job_backend.resumes.review.review import document_hash
from tests.resumes.helpers import resume
from tests.resumes.pdf_helpers import pdf_bytes
from tests.resumes.test_render import generated_resume


def test_reports_missing_fields() -> None:
    source = resume()
    document = generated_resume()
    target = TailoringJob(
        company="Example",
        title="Intern",
        raw_description="Required skills:\n- Python\n- Kubernetes",
    )
    pdf = pdf_bytes(text="Education Technical Skills Experience Projects Awards JavaScript")
    report = diagnose_pdf(document, pdf, source, target)
    assert (
        report.extracted_text == "Education Technical Skills Experience Projects Awards JavaScript"
    )
    assert report.pdf_sha256 == hashlib.sha256(pdf).hexdigest()
    assert report.document_sha256 == document_hash(document)
    checks = {check.key: check for check in report.checks}
    assert checks["identity"].status == "warning" and source.name in checks["identity"].missing
    assert checks["dates"].status == "warning"
    assert checks["headings"].status == "passed"
    assert report.missing_supported_skills == ["Python"]
    assert report.unsupported_required_skills == ["Kubernetes"]
    assert report.matched_required_skills == []


def test_complete_pdf_passes() -> None:
    source = resume()
    document = generated_resume()
    dates = [
        value
        for entry in [*source.education, *source.experience, *source.projects]
        for value in [entry.start_date, entry.end_date]
        if value
    ]
    text = " ".join(
        [
            source.name,
            source.email or "",
            source.phone or "",
            "Education Experience Projects Technical Skills Awards",
            *dates,
            "Python JavaScript",
        ]
    )
    target = TailoringJob(
        company="Example", title="Intern", raw_description="Required skills:\n- Python\n- Java"
    )
    report = diagnose_pdf(document, pdf_bytes(text=text), source, target)
    checks = {check.key: check for check in report.checks}
    assert all(checks[key].status == "passed" for key in ["identity", "dates", "headings", "order"])
    assert report.matched_required_skills == ["Python"]
    assert "Java" not in report.matched_required_skills
    assert normalize_pdf_text("Master\u2019s  2024\u20132026 \ufb01le") == "master's 2024-2026 file"
