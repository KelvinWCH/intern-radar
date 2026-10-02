import hashlib
import re
import unicodedata
from collections.abc import Sequence
from io import BytesIO

from pydantic import JsonValue
from pypdf import PdfReader

from job_backend.jobs.models import TailoringJob
from job_backend.profile.required_skills import (
    extract_required_skills,
    matches_skill,
    matches_term,
    normalize_required_skills,
)
from job_backend.profile.tailoring import candidate_evidence
from job_backend.resumes.models import (
    GeneratedCoverLetter,
    GeneratedResume,
    PdfDiagnosticCheck,
    PdfDiagnostics,
    UserResume,
)
from job_backend.resumes.review.review import document_hash

_NOT_PRINTED = {"ai_usage", "requirement_coverage"}


def _strings(value: JsonValue) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    return []


def normalize_pdf_text(value: str) -> str:
    folded = unicodedata.normalize("NFKC", value).translate(
        str.maketrans({"\u2019": "'", "\u2018": "'", "\u2013": "-", "\u2014": "-"})
    )
    return " ".join(folded.casefold().split())


def diagnose_pdf(
    document: GeneratedResume | GeneratedCoverLetter,
    pdf: bytes,
    profile: UserResume,
    job: TailoringJob,
    keywords: Sequence[str] = (),
) -> PdfDiagnostics:
    reader = PdfReader(BytesIO(pdf), strict=True)
    raw = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = normalize_pdf_text(raw)
    checks: list[PdfDiagnosticCheck] = [
        PdfDiagnosticCheck(
            key="pages",
            label="Page count",
            status="passed" if len(reader.pages) == 1 else "warning",
            detail=f"{len(reader.pages)} page(s); the application requires one page.",
        ),
        PdfDiagnosticCheck(
            key="text",
            label="Selectable text",
            status="passed" if raw.strip() and "\ufffd" not in raw else "warning",
            detail=f"Extracted {len(raw)} characters using pypdf. Inspect the raw text below.",
        ),
    ]

    def check_values(key: str, label: str, values: list[str]) -> None:
        expected = list(dict.fromkeys(value for value in values if value.strip()))
        missing = [value for value in expected if normalize_pdf_text(value) not in text]
        checks.append(
            PdfDiagnosticCheck(
                key=key,
                label=label,
                status="warning" if missing else "passed" if expected else "info",
                detail=f"{len(expected) - len(missing)} of {len(expected)} expected values found."
                if expected
                else "No values supplied for this check.",
                missing=missing,
            )
        )

    check_values(
        "identity",
        "Name and contact details",
        [document.name, *[value for value in [document.email, document.phone] if value]],
    )
    headings: list[str] = []
    if isinstance(document, GeneratedResume):
        headings = [
            title
            for title, entries in [
                ("Education", document.education),
                ("Experience", document.experience),
                ("Projects", document.projects),
                ("Technical Skills", [group for group in document.skills if group.items]),
            ]
            if entries
        ] + [section.title for section in document.additional_sections]
        check_values("headings", "Section headings", headings)
        check_values(
            "dates",
            "Education and experience dates",
            [
                value
                for entry in [*document.education, *document.experience, *document.projects]
                for value in [entry.start_date, entry.end_date]
                if value
            ],
        )
        positions = [text.find(normalize_pdf_text(heading)) for heading in headings]
        order_ok = all(position >= 0 for position in positions) and positions == sorted(positions)
        checks.append(
            PdfDiagnosticCheck(
                key="order",
                label="Section reading order",
                status="passed" if order_ok else "warning",
                detail="Headings follow template order; inspect extracted text for line order."
                if order_ok
                else "A heading is missing or out of order. Inspect the extracted text.",
            )
        )
    else:
        check_values(
            "letter",
            "Company, role and closing",
            [document.company, document.job_title, document.greeting, document.closing],
        )
    evidence = candidate_evidence(profile)
    required = normalize_required_skills(
        job.qualifications.required_skills if job.qualifications else []
    )
    required = required or extract_required_skills(job.raw_description)
    supported = [skill for skill in required if matches_skill(skill, evidence)]
    matched = [skill for skill in supported if matches_skill(skill, raw)]
    missing = [skill for skill in supported if skill not in matched]
    gaps = [skill for skill in required if skill not in supported]
    checks.append(
        PdfDiagnosticCheck(
            key="skills",
            label="Supported required skills",
            status="warning" if missing and isinstance(document, GeneratedResume) else "info",
            detail="Checks explicit names and known aliases against profile evidence and PDF text. "
            "Cover letters need not repeat every skill. This is not an ATS score.",
            missing=missing,
        )
    )
    written = "\n".join(_strings(document.model_dump(mode="json", exclude=_NOT_PRINTED)))
    terms = list({term.casefold(): term for term in [*keywords, *required]}.values())
    supported_terms = [term for term in terms if matches_term(term, evidence, umbrella=True)]
    shown_terms = [term for term in supported_terms if matches_term(term, written)]
    missing_terms = [term for term in supported_terms if term not in shown_terms]
    checks.append(
        PdfDiagnosticCheck(
            key="keywords",
            label="Job keywords",
            status="warning" if missing_terms and isinstance(document, GeneratedResume) else "info",
            detail=f"{len(shown_terms)} of {len(supported_terms)} posting keywords your profile "
            f"supports appear in this document; {len(terms) - len(supported_terms)} are not in "
            "your profile. Missing supported keywords go to the next revision.",
            missing=missing_terms,
        )
    )
    if re.search(r"(?:19|20)\d{2}\s*[\u2010-\u2015\u2212]", raw):
        checks.append(
            PdfDiagnosticCheck(
                key="date_punctuation",
                label="Date punctuation",
                status="info",
                detail="A year is followed by a Unicode dash. Check imported dates if an "
                "employer's form reads this differently; this alone is not a parsing failure.",
            )
        )
    return PdfDiagnostics(
        document="resume" if isinstance(document, GeneratedResume) else "cover_letter",
        document_sha256=document_hash(document),
        pdf_sha256=hashlib.sha256(pdf).hexdigest(),
        page_count=len(reader.pages),
        extracted_text=raw,
        checks=checks,
        matched_required_skills=matched,
        missing_supported_skills=missing,
        unsupported_required_skills=gaps,
        matched_keywords=shown_terms,
        missing_supported_keywords=missing_terms,
        unsupported_keywords=[term for term in terms if term not in supported_terms],
    )
