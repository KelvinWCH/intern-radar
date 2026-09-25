import pytest
from pydantic import ValidationError

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.github.github_sources.simplify_internships import (
    FEED_URL,
    scrape_listings,
)
from tests.helpers import listing, payload


def test_selects_season() -> None:
    result = scrape_listings(payload(listing(), listing("other", term="Summer 2026")))
    assert result.fetched == 2 and len(result.links) == 1
    assert result.documents == []
    link = result.links[0]
    assert link.url == "https://example.com/jobs/example-1"
    assert link.external_id == "example-1" and link.date_posted == 1790000000
    assert link.listing_url == FEED_URL


def test_rejects_bad_feed() -> None:
    with pytest.raises(SourceDataError):
        scrape_listings(b"[]")
    with pytest.raises(ValidationError):
        scrape_listings(b'{"error": "not a job list"}')
    with pytest.raises(SourceDataError, match="application URLs"):
        scrape_listings(payload({"unfamiliar": "no application link"}))
