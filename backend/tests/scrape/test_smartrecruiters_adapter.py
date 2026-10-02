import httpx2
from pydantic import JsonValue

from job_backend.scrape.companies.models import Company
from job_backend.scrape.pipeline.heuristics.parsing import read_record
from job_backend.scrape.smartrecruiters import smartrecruiters


def _company() -> Company:
    return Company(
        key="ubisoft",
        name="Ubisoft",
        job_board="smartrecruiters",
        board_name="Ubisoft2",
        careers_url="https://jobs.smartrecruiters.com/Ubisoft2",
    )


def _listing(identifier: str, name: str = "Gameplay Programmer Intern") -> dict[str, JsonValue]:
    return {
        "id": identifier,
        "name": name,
        "refNumber": f"REF{identifier}",
        "location": {"city": "Montreal", "region": "QC", "country": "ca", "remote": False},
        "releasedDate": "2026-10-01T00:00:00.000Z",
        "typeOfEmployment": {"label": "Intern"},
    }


def _detail(identifier: str) -> dict[str, JsonValue]:
    return {
        **_listing(identifier),
        "jobAd": {
            "sections": {
                "jobDescription": {"title": "Job Description", "text": "<p>Build gameplay.</p>"},
                "qualifications": {"title": "Qualifications", "text": "<p>Enrolled student.</p>"},
            }
        },
        "postingUrl": f"https://jobs.smartrecruiters.com/Ubisoft2/{identifier}-intern",
        "applyUrl": f"https://jobs.smartrecruiters.com/Ubisoft2/{identifier}-intern?apply",
    }


def test_smartrecruiters_canada() -> None:
    requests: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(str(request.url))
        if request.url.path.endswith("/postings"):
            assert request.url.params["country"] == "ca"
            offset = int(request.url.params["offset"])
            content = [_listing("1"), _listing("2"), _listing("1")] if offset == 0 else []
            return httpx2.Response(200, json={"totalFound": 2, "content": content})
        identifier = request.url.path.rsplit("/", 1)[-1]
        return httpx2.Response(200, json=_detail(identifier))

    fetched = smartrecruiters.fetch_postings(
        _company(), None, transport=httpx2.MockTransport(respond)
    )
    assert fetched.payload is not None and not fetched.failures
    assert sum(url.endswith("offset=0") for url in requests) == 1
    scraped = smartrecruiters.scrape_postings(_company(), fetched.payload)
    assert scraped.fetched == 2
    first = scraped.documents[0]
    assert first.external_id == "1"
    assert first.application_url == "https://jobs.smartrecruiters.com/Ubisoft2/1-intern"
    assert first.apply_url == "https://jobs.smartrecruiters.com/Ubisoft2/1-intern?apply"
    record = read_record(first)
    job = record["job"]
    assert isinstance(job, dict)
    assert job["title"] == "Gameplay Programmer Intern"
    assert job["locations"] == ["Montreal, QC, ca"]
    assert job["employmentType"] == "Intern"
    assert "<h3>Qualifications</h3>" in str(job["description"])
    unchanged = smartrecruiters.fetch_postings(
        _company(), fetched.etag, transport=httpx2.MockTransport(respond)
    )
    assert unchanged.payload is None
