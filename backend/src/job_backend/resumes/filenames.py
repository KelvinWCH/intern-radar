import re
import unicodedata
from typing import Literal

DocumentKind = Literal["resume", "cover-letter", "transcript", "application"]

_SUFFIXES: dict[DocumentKind, str] = {
    "resume": "",
    "cover-letter": "Cover_Letter",
    "transcript": "Transcript",
    "application": "Application",
}


def document_filename(company: str, applicant: str, kind: DocumentKind, extension: str) -> str:
    parts = [_words(company), _words(applicant), _SUFFIXES[kind]]
    stem = "_".join(part for part in parts if part) or kind
    return f"{stem}.{extension}"


def _words(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    ascii_text = ascii_text.replace("&", " and ")
    return "_".join(re.findall(r"[A-Za-z0-9]+", ascii_text))[:80].strip("_")
