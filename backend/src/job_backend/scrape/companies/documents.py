import json

from pydantic import JsonValue

from job_backend.scrape.companies.models import Company
from job_backend.scrape.pipeline.models import RawDocument


def job_document(
    company: Company,
    record: dict[str, JsonValue],
    *,
    feed_url: str,
    external_id: str,
    application_url: str,
    apply_url: str | None,
) -> RawDocument:
    return RawDocument(
        content=json.dumps(
            {"company_name": company.name, "job": record}, ensure_ascii=False, sort_keys=True
        ),
        source_url=feed_url,
        media_type="application/json",
        external_id=external_id,
        listing_url=company.careers_url,
        application_url=application_url,
        apply_url=apply_url,
    )
