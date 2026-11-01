import json
import re
from html import unescape
from html.parser import HTMLParser
from itertools import islice

from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.constants import (
    CSS_BLOCK,
    DESCRIPTION_ALTERNATIVE_SECTIONS,
    DESCRIPTION_ENVELOPES,
    DESCRIPTION_FIELDS,
    DESCRIPTION_SECTIONS,
    HTML_ENTITY,
    HTML_TAG,
    HTML_TAG_NAMES,
    SCRIPT_LINE,
    TAILORING_DESCRIPTION_LIMIT,
)
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.heuristics.parsing import read_record
from job_backend.scrape.pipeline.models import RawDocument


class _DescriptionText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "noscript", "template", "head"}:
            self.ignored.append(tag)
        elif not self.ignored and tag in {"p", "div", "li", "br", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")
        elif not self.ignored and tag not in HTML_TAG_NAMES:
            self.parts.append(self.get_starttag_text() or f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if self.ignored and tag == self.ignored[-1]:
            self.ignored.pop()
        elif not self.ignored and tag in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")
        elif not self.ignored and tag not in HTML_TAG_NAMES:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def _clean_text(text: str) -> str:
    for _ in range(2):
        if HTML_TAG.search(text):
            break
        decoded = HTML_ENTITY.sub(lambda match: unescape(match.group()), text)
        if decoded == text:
            break
        text = decoded
    if HTML_TAG.search(text):
        parser = _DescriptionText()
        parser.feed(text)
        parser.close()
        text = "".join(parser.parts)
    for _ in range(8):
        cleaned = CSS_BLOCK.sub("", text)
        if cleaned == text:
            break
        text = cleaned
    text = SCRIPT_LINE.sub("", text)
    lines = [re.sub(r"[\t \u00a0]+", " ", line).strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _append_section(parts: list[str], rendered: list[str], section: str) -> bool:
    comparable = " ".join(_clean_text(section).split())
    if not comparable:
        return False
    pattern = re.compile(r"(?<!\w)" + re.escape(comparable) + r"(?!\w)")
    if any(pattern.search(existing) for existing in rendered):
        return False
    parts.append(section)
    rendered.append(comparable)
    return True


def _structured_description(value: JsonValue) -> str | None:
    if isinstance(value, list):
        return next((found for item in value if (found := _structured_description(item))), None)
    if not isinstance(value, dict):
        return None
    for key in DESCRIPTION_ENVELOPES:
        found = _structured_description(value.get(key))
        if found:
            return found
    kind = value.get("@type")
    if (
        kind is not None
        and kind != "JobPosting"
        and not (isinstance(kind, list) and "JobPosting" in kind)
    ):
        return None
    description = next(
        (
            text
            for key in DESCRIPTION_FIELDS
            if isinstance(text := value.get(key), str) and _clean_text(text)
        ),
        None,
    )
    if not isinstance(description, str):
        return None
    parts = [description]
    rendered = [" ".join(_clean_text(description).split())]
    header = value.get("jobDescriptionHeader")
    if isinstance(header, str) and _append_section(parts, rendered, header):
        parts.insert(0, parts.pop())
    sections = value.get("lists")
    if isinstance(sections, list):
        for section in sections:
            if isinstance(section, dict):
                for key in ("text", "content"):
                    if isinstance(text := section.get(key), str):
                        _append_section(parts, rendered, text)
    for alternatives in DESCRIPTION_ALTERNATIVE_SECTIONS:
        for key in alternatives:
            if isinstance(text := value.get(key), str) and _clean_text(text):
                _append_section(parts, rendered, text)
                break
    for key in DESCRIPTION_SECTIONS:
        text = value.get(key)
        if isinstance(text, str):
            _append_section(parts, rendered, text)
        elif isinstance(text, list):
            for item in text:
                if isinstance(item, str):
                    _append_section(parts, rendered, item)
    return "\n\n".join(parts)


def _description_from_json(raw: str) -> str | None:
    decoder = json.JSONDecoder()
    if raw.lstrip().startswith('"'):
        try:
            decoded: object = json.loads(raw)
            if isinstance(decoded, str):
                raw = decoded
        except ValueError:
            pass
    for match in islice(re.finditer(r"[\[{]", raw), 128):
        try:
            value, _ = decoder.raw_decode(raw, match.start())
            description = _structured_description(TypeAdapter(JsonValue).validate_python(value))
        except ValueError:
            continue
        if description:
            return description
    return None


def _unwrap_source(raw: str) -> str:
    for _ in range(3):
        if raw.lstrip().startswith(("{", "[", '"')):
            try:
                decoded: object = json.loads(raw)
                if isinstance(decoded, str):
                    raw = decoded
                    continue
                break
            except ValueError:
                pass
        if HTML_TAG.search(raw):
            break
        unescaped = HTML_ENTITY.sub(lambda match: unescape(match.group()), raw)
        if unescaped == raw:
            break
        raw = unescaped
    return raw


def clean_description(raw: str | None, *, source_url: str | None = None) -> str | None:
    if raw is None:
        return None
    candidate = _unwrap_source(raw)
    text = candidate
    description = None
    is_html = not candidate.lstrip().startswith(("{", "[")) and bool(HTML_TAG.search(candidate))
    matched_json = False
    if source_url and candidate.strip():
        try:
            record = read_record(
                RawDocument(
                    content=candidate,
                    source_url=source_url,
                    media_type="text/html" if is_html else "application/json",
                )
            )
            description = _structured_description(record)
            matched_json = not is_html
        except (ValueError, SourceDataError):
            pass
    if description:
        text = description
    elif matched_json:
        text = ""
    elif not (source_url and is_html):
        for _ in range(3):
            description = _description_from_json(candidate)
            if description:
                text = description
                break
            decoded = unescape(candidate)
            if decoded == candidate:
                break
            candidate = decoded
    return _clean_text(text)


def description_for_tailoring(
    raw: str | None, cleaned: str | None, *, allow_empty: bool = False
) -> str:
    text = cleaned if cleaned is not None else clean_description(raw)
    if not text or not text.strip():
        if allow_empty:
            return ""
        raise ValueError("Add a cleaned job description before tailoring documents.")
    if len(text) > TAILORING_DESCRIPTION_LIMIT:
        raise ValueError(
            f"The cleaned description has {len(text):,} characters, "
            f"{len(text) - TAILORING_DESCRIPTION_LIMIT:,} over the "
            f"{TAILORING_DESCRIPTION_LIMIT:,}-character tailoring limit. "
            "Edit the cleaned description "
            "to remove remaining page code or unrelated text; the raw description is preserved."
        )
    return text
