import time

from pydantic import JsonValue, TypeAdapter

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.github.utils.dates import parse_posted_date
from job_backend.scrape.pipeline.models import JobLink, ScrapeResult


def collect_json_links(
    payload: bytes,
    file_url: str,
    *,
    term: str | None = None,
    records_key: str | None = None,
    id_key: str = "id",
    url_key: str = "url",
    date_key: str = "date_posted",
) -> ScrapeResult:
    validator = TypeAdapter(list[dict[str, JsonValue]])
    if records_key is None:
        records = validator.validate_json(payload, strict=True)
    else:
        envelope = TypeAdapter(dict[str, JsonValue]).validate_json(payload, strict=True)
        if records_key not in envelope:
            raise SourceDataError(f"GitHub job data is missing its {records_key!r} array")
        records = validator.validate_python(envelope[records_key], strict=True)
    if not records:
        raise SourceDataError("Refusing an unexpectedly empty GitHub job list")
    links: list[JobLink] = []
    now = int(time.time())
    selected = 0
    for record in records:
        terms = record.get("terms")
        if term is not None and isinstance(terms, list) and term not in terms:
            continue
        selected += 1
        url = record.get(url_key)
        if not isinstance(url, str) or not url:
            continue
        external_id = record.get(id_key)
        links.append(
            JobLink(
                url=url,
                listing_url=file_url,
                date_posted=parse_posted_date(record.get(date_key), now=now),
                external_id=external_id if isinstance(external_id, str) and external_id else None,
                listing_data=record,
            )
        )
    if selected and not links:
        raise SourceDataError("No application URLs found; the GitHub JSON format may have changed")
    return ScrapeResult(fetched=len(records), links=links)
