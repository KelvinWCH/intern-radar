import re
from html import unescape
from urllib.parse import urlsplit

from pydantic import JsonValue, TypeAdapter

from job_backend.scrape.eightfold.constants import BOARD_DOMAINS as EIGHTFOLD_DOMAINS
from job_backend.scrape.eightfold.record import page_record as eightfold_record
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.github.utils.dates import parse_posted_date
from job_backend.scrape.hibob.constants import CAREERS_HOST_SUFFIX as HIBOB_HOST_SUFFIX
from job_backend.scrape.hibob.record import page_record as hibob_record
from job_backend.scrape.lever.record import page_record as lever_record
from job_backend.scrape.oracle.record import page_record as oracle_record
from job_backend.scrape.pipeline.heuristics.classification import (
    classify_locations,
    internship_title,
)
from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.pages import provider_page
from job_backend.scrape.pipeline.heuristics.structured import (
    job_postings,
    select_posting,
    structured_record,
)
from job_backend.scrape.pipeline.models import RawDocument
from job_backend.scrape.recruitee.constants import API_HOST_SUFFIX as RECRUITEE_SUFFIX
from job_backend.scrape.recruitee.record import page_record as recruitee_record
from job_backend.scrape.smartrecruiters.constants import API_ROOT as SMARTRECRUITERS_ROOT
from job_backend.scrape.smartrecruiters.record import page_record as smartrecruiters_record
from job_backend.scrape.utils.constants import EIGHTFOLD_HOST_SUFFIX
from job_backend.scrape.utils.page_text import page_text
from job_backend.scrape.workable.record import page_record as workable_record
from job_backend.scrape.workday.record import page_record as workday_record


def text_value(value: JsonValue) -> str | None:
    return unescape(value).strip() or None if isinstance(value, str) else None


def object_value(value: JsonValue) -> dict[str, JsonValue]:
    return value if isinstance(value, dict) else {}


def record_posted_date(record: dict[str, JsonValue]) -> int | None:
    for key in ("date_posted", "datePosted", "publishedAt", "published_at", "first_published"):
        timestamp = parse_posted_date(record.get(key))
        if timestamp is not None:
            return timestamp
    return None


def location_values(value: JsonValue, *, postal_address: JsonValue = None) -> list[str]:
    if postal_address is not None:
        labels = location_values(value)
        addresses = location_values(postal_address)
        if not labels or not addresses:
            return labels or addresses
        return [
            ", ".join(dict.fromkeys([part.strip(), *addresses]))
            for label in labels
            for part in re.split(r"[;|\n]", label)
            if part.strip()
        ]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [location for item in value for location in location_values(item)]
    if isinstance(value, dict):
        address = value.get("address")
        if address is not None:
            postal_address = object_value(address).get("postalAddress")
            if postal_address is not None:
                return location_values(
                    value.get("name") or value.get("location"), postal_address=postal_address
                )
            return location_values(address)
        if value.get("postalAddress") is not None:
            return location_values(value["postalAddress"])
        parts = [
            text_value(value.get(key)) or text_value(object_value(value.get(key)).get("name"))
            for key in ("addressLocality", "addressRegion", "addressCountry")
        ]
        if parts[-1] in {"CA", "CAN"}:
            parts[-1] = "Canada"
        elif parts[-1] in {"US", "USA"}:
            parts[-1] = "United States"
        if any(parts):
            return [", ".join(part for part in parts if part)]
        return location_values(value.get("name") or value.get("location"))
    return []


def _labelled_fields(text: str) -> dict[str, JsonValue]:
    fields: dict[str, JsonValue] = {}
    for key, label in (
        ("title", "(?:job title|title|role)"),
        ("company_name", "company"),
        ("locations", "location(?:s)?"),
    ):
        separator = ":" if key == "company_name" else "(?::|\n)"
        match = re.search(rf"(?im)^\s*{label}\s*{separator}\s*([^\n]+)$", text)
        if match:
            fields[key] = match.group(1).strip()
    posted = re.search(
        r"(?im)^\s*(?:date posted|posted on|posting date|date published|published on|posted)"
        r"(?:\s*:\s*|\s+)([^\n]+)$",
        text,
    )
    if posted:
        fields["date_posted"] = posted.group(1).strip()
    if not fields.get("title"):
        title = next(
            (
                line.strip()
                for line in text.splitlines()
                if 5 < len(line.strip()) < 160 and internship_title(line)
            ),
            None,
        )
        if title:
            parts = re.split(r"\s+(?:at|@)\s+", title, maxsplit=1)
            fields["title"] = parts[0]
            if len(parts) == 2:
                fields.setdefault("company_name", parts[1])
    if not fields.get("locations"):
        fields["locations"] = "; ".join(
            line.strip()
            for line in text.splitlines()
            if len(line.strip()) < 100 and classify_locations([line])[0]
        )
    return fields


def read_record(document: RawDocument) -> dict[str, JsonValue]:
    if document.media_type in {"application/json", "application/ld+json"}:
        value = TypeAdapter(JsonValue).validate_json(document.content)
        postings = job_postings(value)
        if postings:
            return select_posting(postings, document)
        envelope = object_value(value)
        row = object_value(envelope.get("job"))
        host = urlsplit(document.source_url).hostname or ""
        if row and host.endswith(".myworkdayjobs.com"):
            return {**envelope, "job": workday_record(row)}
        if row and host in {"www.workable.com", "apply.workable.com", "workable.com"}:
            return {**envelope, "job": workable_record(row)}
        if row and host in {"api.lever.co", "api.eu.lever.co"}:
            return {**envelope, "job": lever_record(row)}
        if row and (host in EIGHTFOLD_DOMAINS or host.endswith(EIGHTFOLD_HOST_SUFFIX)):
            return {**envelope, "job": eightfold_record(row)}
        if row and host.endswith(HIBOB_HOST_SUFFIX):
            return {**envelope, "job": hibob_record(row)}
        if row and document.source_url.startswith(SMARTRECRUITERS_ROOT):
            return {**envelope, "job": smartrecruiters_record(row)}
        if row and host.endswith(RECRUITEE_SUFFIX):
            return {**envelope, "job": recruitee_record(row)}
        if row and host.endswith(".oraclecloud.com"):
            return {**envelope, "job": oracle_record(row)}
        return envelope
    markup = PageMarkup(document.content) if "html" in document.media_type else None
    facts = provider_page(markup, document.source_url) if markup is not None else None
    structured = structured_record(document, markup, facts.title if facts else None)
    for key in ("title", "company_name", "company"):
        if key in structured and text_value(structured[key]) is None:
            structured.pop(key)
    for key in ("locations", "location", "jobLocation"):
        if key in structured and not location_values(structured[key]):
            structured.pop(key)
    if "hiringOrganization" in structured and not text_value(
        object_value(structured["hiringOrganization"]).get("name")
    ):
        structured.pop("hiringOrganization")
    for key in ("datePosted", "date_posted"):
        if key in structured and parse_posted_date(structured[key]) is None:
            structured.pop(key)
    identifier = structured.get("identifier")
    if object_value(identifier).get("@type") == "URL":
        identifier = None
        structured.pop("identifier", None)
    identifier_value = (
        object_value(identifier).get("value") if isinstance(identifier, dict) else identifier
    )
    if not (
        text_value(identifier_value)
        or (isinstance(identifier_value, int) and not isinstance(identifier_value, bool))
    ):
        structured.pop("identifier", None)
    try:
        text = page_text(document.content, include_structured=False) if markup else document.content
    except SourceDataError:
        if not structured:
            raise
        text = ""
    fields = _labelled_fields(text)
    if facts is not None:
        if facts.title:
            fields["title"] = facts.title
        if facts.company_name:
            fields["company_name"] = facts.company_name
        if facts.locations:
            fields["locations"] = list(facts.locations)
        if facts.source_job_id:
            fields["identifier"] = {"value": facts.source_job_id}
        if facts.date_posted:
            fields["date_posted"] = facts.date_posted
        if facts.apply_url:
            fields["apply_url"] = facts.apply_url
        if facts.description:
            structured["description"] = facts.description
    if any(structured.get(key) for key in ("jobLocation", "location", "locations")):
        fields.pop("locations", None)
    if any(structured.get(key) for key in ("company", "company_name", "hiringOrganization")):
        fields.pop("company_name", None)
    if any(structured.get(key) for key in ("datePosted", "date_posted")):
        fields.pop("date_posted", None)
    return {**fields, **structured}
