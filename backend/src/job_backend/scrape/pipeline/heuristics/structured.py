import json
import re
from itertools import islice
from urllib.parse import parse_qsl, urlsplit

from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.models import RawDocument


def job_postings(value: JsonValue) -> list[dict[str, JsonValue]]:
    if isinstance(value, list):
        return [posting for item in value for posting in job_postings(item)]
    if not isinstance(value, dict):
        return []
    kind = value.get("@type")
    if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
        return [value]
    return job_postings(value.get("@graph"))


def _url_identity(url: str) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    parsed = urlsplit(url)
    parameters = tuple(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query)
            if not key.startswith("utm_") and key not in {"source", "src", "ref", "trk", "gh_src"}
        )
    )
    return (parsed.hostname or "", parsed.path.rstrip("/"), parameters)


def select_posting(
    postings: list[dict[str, JsonValue]], document: RawDocument, title: str | None = None
) -> dict[str, JsonValue]:
    unique: list[dict[str, JsonValue]] = []
    for posting in postings:
        if posting not in unique:
            unique.append(posting)
    identities = {_url_identity(document.source_url)}
    if document.application_url:
        identities.add(_url_identity(document.application_url))
    matching_urls = [
        posting
        for posting in unique
        if isinstance(url := posting.get("url"), str) and _url_identity(url) in identities
    ]
    if len(matching_urls) == 1:
        return matching_urls[0]
    if title:
        matching_titles = [
            posting
            for posting in unique
            if isinstance(value := posting.get("title"), str)
            and value.strip().casefold() == title.strip().casefold()
        ]
        if len(matching_titles) == 1:
            return matching_titles[0]
    if len(unique) == 1 and not unique[0].get("url"):
        return unique[0]
    return {}


def structured_record(
    document: RawDocument, markup: PageMarkup | None, title: str | None = None
) -> dict[str, JsonValue]:
    postings: list[dict[str, JsonValue]] = []
    if markup is not None:
        for element in markup.elements:
            if (
                element.tag != "script"
                or (element.attributes.get("type") or "").lower().split(";", 1)[0]
                != "application/ld+json"
            ):
                continue
            try:
                value = TypeAdapter(JsonValue).validate_json("".join(element.parts))
                postings.extend(job_postings(value))
            except ValidationError:
                continue
    else:
        for match in islice(re.finditer(r"[\[{]", document.content), 128):
            try:
                value, _ = json.JSONDecoder().raw_decode(document.content[match.start() :])
                postings.extend(job_postings(TypeAdapter(JsonValue).validate_python(value)))
            except (ValueError, ValidationError):
                continue
    return select_posting(postings, document, title)
