from urllib.parse import urlsplit

from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.models import PageFacts
from job_backend.scrape.rippling.constants import PAGE_DATA_ID, PAGE_HOSTS
from job_backend.scrape.rippling.models import RipplingPageJob


def extract_page(markup: PageMarkup, source_url: str) -> PageFacts:
    source = urlsplit(source_url)
    if source.hostname not in PAGE_HOSTS:
        return PageFacts()
    for element in markup.elements:
        if element.tag != "script" or element.attributes.get("id") != PAGE_DATA_ID:
            continue
        try:
            value: JsonValue = TypeAdapter(JsonValue).validate_json("".join(element.parts))
            for key in ("props", "pageProps", "apiData", "jobPost"):
                value = value.get(key) if isinstance(value, dict) else None
            posting = RipplingPageJob.model_validate(value)
            target = urlsplit(posting.url)
            if target.hostname not in PAGE_HOSTS or target.path.rstrip("/") != source.path.rstrip(
                "/"
            ):
                continue
            return PageFacts(
                title=posting.name,
                company_name=posting.companyName,
                locations=posting.workLocations,
                source_job_id=posting.uuid,
                description="\n".join(
                    section
                    for section in (posting.description.company, posting.description.role)
                    if section
                ),
            )
        except (ValidationError, ValueError):
            continue
    return PageFacts()
