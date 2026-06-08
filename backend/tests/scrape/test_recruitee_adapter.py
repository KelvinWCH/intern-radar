import json

from pydantic import JsonValue

from job_backend.scrape.companies.models import Company
from job_backend.scrape.pipeline.targeting import document_is_candidate
from job_backend.scrape.recruitee import recruitee


def _company() -> Company:
    return Company(
        key="example",
        name="Example Research Canada",
        job_board="recruitee",
        board_name="examplecanada",
        careers_url="https://examplecanada.recruitee.com/",
    )


def _offer(identifier: int, title: str, city: str, country: str) -> dict[str, JsonValue]:
    slug = title.lower().replace(" ", "-")
    return {
        "id": identifier,
        "title": title,
        "slug": slug,
        "status": "published",
        "careers_url": f"https://examplecanada.recruitee.com/o/{slug}",
        "careers_apply_url": f"https://examplecanada.recruitee.com/o/{slug}/c/new",
        "description": "<p>Research compilers for AI accelerators.</p>",
        "requirements": "<ul><li>Graduate student in computer science</li></ul>",
        "location": f"{city}, {country}",
        "locations": [{"id": 1, "name": city, "city": city, "country": country}],
        "employment_type_code": "internship",
        "published_at": "2026-10-20 14:05:00 UTC",
        "remote": False,
    }


def _payload(*offers: dict[str, JsonValue]) -> bytes:
    return json.dumps({"offers": list(offers)}).encode()


def test_recruitee_feed() -> None:
    scraped = recruitee.scrape_postings(
        _company(),
        _payload(
            _offer(1, "Compiler Research Intern", "Markham", "Canada"),
            _offer(2, "Senior Engineer", "Shenzhen", "China"),
        ),
    )
    assert recruitee.feed_url(_company()) == "https://examplecanada.recruitee.com/api/offers/"
    assert scraped.fetched == 2
    first = scraped.documents[0]
    assert first.external_id == "1"
    assert first.application_url == "https://examplecanada.recruitee.com/o/compiler-research-intern"
    assert first.apply_url == first.application_url + "/c/new"
    assert document_is_candidate(first)
    assert not document_is_candidate(scraped.documents[1])
