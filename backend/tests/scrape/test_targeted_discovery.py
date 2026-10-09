import json

import pytest
from pydantic import JsonValue

from job_backend.persistence.database import Database
from job_backend.scrape.pipeline.models import (
    FetchResult,
    RawDocument,
)
from job_backend.scrape.pipeline.pipeline import scrape_source
from job_backend.scrape.pipeline.targeting import document_is_candidate
from tests.helpers import ADAPTER, StubNormalizer, listing, payload


def _provider_document(provider: str, title: str, location: str) -> RawDocument:
    record: dict[str, JsonValue] = {"title": title, "locations": [location]}
    origin = "https://example.com/feed"
    if provider == "lever":
        origin = "https://api.lever.co/v0/postings/example"
        record = {"text": title, "categories": {"location": location}}
    elif provider == "greenhouse":
        record = {"title": title, "location": {"name": location}, "content": "Full description"}
    elif provider == "ashby":
        record = {"title": title, "location": location, "descriptionPlain": "Full description"}
    elif provider == "workable":
        origin = "https://www.workable.com/api/accounts/example"
        record = {"title": title, "locations": [{"country": location}]}
    elif provider == "hibob":
        origin = "https://example.careers.hibob.com/api/public/jobs"
        record = {"title": title, "site": location}
    elif provider == "workday":
        origin = "https://example.wd5.myworkdayjobs.com/wday/cxs/example/Careers/jobs"
        record = {"detail": {"jobPostingInfo": {"title": title, "location": location}}}
    elif provider == "eightfold":
        origin = "https://careers.qualcomm.com/api/pcsx/position_details"
        record = {"detail": {"data": {"name": title, "locations": [location]}}}
    return RawDocument(
        content=json.dumps({"company_name": "Example", "job": record}),
        source_url=origin,
        media_type="application/json",
    )


@pytest.mark.parametrize("provider", ["lever", "greenhouse"])
@pytest.mark.parametrize(
    ("title", "location", "expected"),
    [("Software Intern", "Canada", True), ("Software Intern", "United States", False)],
)
def test_projections_share_scope(provider: str, title: str, location: str, expected: bool) -> None:
    document = _provider_document(provider, title, location)
    original = document.content
    assert document_is_candidate(document) is expected
    assert document.content == original


def test_unrelated_docs_skip_budget(engine: Database) -> None:
    records = [listing(str(index), title="Senior Software Engineer") for index in range(120)]
    records.extend([listing("target-1"), listing("target-2")])
    normalizer = StubNormalizer()
    run = scrape_source(
        engine, ADAPTER, lambda _etag: FetchResult(payload(*records), None), normalizer=normalizer
    )
    assert run.fetched == 122 and run.items_total == 2
    assert run.created == run.items_done == normalizer.calls == 2
