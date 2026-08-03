from io import BytesIO
from pathlib import PurePath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from pypdf import PageObject, PdfReader
from pypdf.errors import PyPdfError
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

from job_backend.resumes.upload_resume.constants import (
    MAX_DOCUMENT_BYTES,
    MAX_LINKS,
    MAX_PDF_PAGES,
    MAX_UPLOAD_BYTES,
    SUPPORTED_EXTENSIONS,
)

_WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class ResumeUploadError(ValueError):
    pass


def extract_resume_text(filename: str, content: bytes, *, max_chars: int) -> str:
    suffix = PurePath(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ResumeUploadError("Upload a .pdf, .docx, .txt, .md, or .tex resume")
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ResumeUploadError("Resume upload must contain between 1 byte and 5 MiB")
    try:
        if suffix == ".pdf":
            text = _read_pdf(content)
        elif suffix == ".docx":
            text = _read_docx(content)
        else:
            text = content.decode("utf-8-sig")
    except (UnicodeError, BadZipFile, ElementTree.ParseError, PyPdfError, OSError, KeyError):
        raise ResumeUploadError(
            "Could not read the resume; use an unencrypted text document"
        ) from None
    if not text.strip() or "\x00" in text:
        raise ResumeUploadError("Resume has no readable text; scanned PDFs need OCR first")
    if len(text) > max_chars:
        raise ResumeUploadError("Resume exceeds JOB_AI_MAX_DOCUMENT_CHARS; shorten the source")
    return text


def _read_pdf(content: bytes) -> str:
    reader = PdfReader(BytesIO(content))
    if reader.is_encrypted:
        raise ResumeUploadError("Upload an unencrypted PDF")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ResumeUploadError("Resume PDF must have at most 20 pages")
    pages: list[str] = []
    targets: list[str] = []
    total = 0
    for page in reader.pages:
        stream = page.get_contents()
        if stream is not None:
            total += len(stream.get_data())
            if total > MAX_DOCUMENT_BYTES:
                raise ResumeUploadError("Expanded PDF content exceeds 20 MiB")
        pages.append(page.extract_text())
        targets.extend(_pdf_link_targets(page))
    return _with_link_targets("\n".join(pages), targets)


def _pdf_link_targets(page: PageObject) -> list[str]:
    annotations = _resolve(page.get("/Annots"))
    if not isinstance(annotations, ArrayObject):
        return []
    targets: list[str] = []
    for item in annotations:
        annotation = _resolve(item)
        action = (
            _resolve(annotation.get("/A")) if isinstance(annotation, DictionaryObject) else None
        )
        uri = _resolve(action.get("/URI")) if isinstance(action, DictionaryObject) else None
        if isinstance(uri, str):
            targets.append(uri)
    return targets


def _resolve(value: object) -> object:
    return value.get_object() if isinstance(value, IndirectObject) else value


def _read_docx(content: bytes) -> str:
    with ZipFile(BytesIO(content)) as archive:
        names = archive.namelist()
        if "word/document.xml" not in names:
            raise ResumeUploadError("Upload a valid Word .docx document")
        parts = [
            "word/document.xml",
            *sorted(
                name
                for name in names
                if name.startswith(("word/header", "word/footer")) and name.endswith(".xml")
            ),
        ]
        if sum(archive.getinfo(name).file_size for name in parts) > MAX_DOCUMENT_BYTES:
            raise ResumeUploadError("Expanded Word text exceeds 20 MiB")
        targets: list[str] = []
        if "word/_rels/document.xml.rels" in names:
            relations = archive.read("word/_rels/document.xml.rels")
            if len(relations) > MAX_DOCUMENT_BYTES or b"<!DOCTYPE" in relations.upper():
                raise ResumeUploadError("Word document relationships are unsupported")
            targets = [
                relation.get("Target", "")
                for relation in ElementTree.fromstring(relations)
                if relation.get("TargetMode") == "External"
                and relation.get("Type", "").endswith("/hyperlink")
            ]
        paragraphs: list[str] = []
        for name in parts:
            xml = archive.read(name)
            if b"<!DOCTYPE" in xml.upper():
                raise ResumeUploadError("Word documents with custom XML entities are unsupported")
            root = ElementTree.fromstring(xml)
            for paragraph in root.iter(_WORD_NAMESPACE + "p"):
                paragraphs.append(
                    "".join(
                        element.text or "" if element.tag == _WORD_NAMESPACE + "t" else " "
                        for element in paragraph.iter()
                        if element.tag
                        in {_WORD_NAMESPACE + "t", _WORD_NAMESPACE + "tab", _WORD_NAMESPACE + "br"}
                    )
                )
        return _with_link_targets("\n".join(paragraphs), targets)


def _with_link_targets(text: str, targets: list[str]) -> str:
    unique = list(dict.fromkeys(target.strip() for target in targets if target.strip()))
    if not text.strip() or not unique:
        return text
    return text + "\n\nHyperlink targets in this document:\n" + "\n".join(unique[:MAX_LINKS])
