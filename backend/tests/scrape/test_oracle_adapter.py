from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest
from pydantic import JsonValue

from job_backend.jobs.descriptions import clean_description
from job_backend.scrape.companies.models import Company
from job_backend.scrape.oracle import oracle
from job_backend.scrape.pipeline.heuristics.normalizer import HeuristicNormalizer

HOST = "fa-example-saasfaprod1.fa.ocs.oraclecloud.com"
CANADA = 300000000471544


def _company() -> Company:
    return Company(
        key="example",
        name="Example Networks",
        careers_url=f"https://{HOST}/hcmUI/CandidateExperience/en/sites/ExampleCareers",
        job_board="oracle",
        board_name="CX_1",
    )


def _summary(identifier: str, title: str, place: str = "Canada") -> dict[str, JsonValue]:
    return {
        "Id": identifier,
        "Title": title,
        "PostedDate": "2026-10-20",
        "PrimaryLocation": place,
        "PrimaryLocationCountry": "CA",
        "JobType": None,
        "secondaryLocations": [],
    }


def _detail(identifier: str, title: str, job_type: str) -> dict[str, JsonValue]:
    return {
        "Id": identifier,
        "Title": title,
        "RequisitionType": "Campus/ trainee",
        "JobType": job_type,
        "ExternalPostedStartDate": "2026-10-02T17:08:46+00:00",
        "PrimaryLocation": "Canada",
        "ExternalDescriptionStr": "<p>Build embedded test tooling.</p>",
        "ExternalResponsibilitiesStr": "<ul><li>Automate lab equipment.</li></ul>",
        "ExternalQualificationsStr": "<ul><li>Enrolled in computer engineering.</li></ul>",
        "workLocation": [
            {"TownOrCity": "Ottawa", "Region2": "Ontario", "Country": "CA", "PostalCode": "K2K"}
        ],
        "requisitionFlexFields": [
            {"Prompt": "Salary Range", "Value": "$47,424 - 91,104 CAD per year"}
        ],
        "secondaryLocations": [],
    }


POSTINGS = {
    "40892": ("Embedded Software Co-op/Intern", "Fixed Term Student Trainee/Apprentice"),
    "40893": ("Senior Director, Product", "Regular"),
    "40894": ("Software Engineer", "Regular"),
}


def _transport(
    details: list[str], *, canada: bool = True, withdrawn: frozenset[str] = frozenset()
) -> httpx2.MockTransport:
    def respond(request: httpx2.Request) -> httpx2.Response:
        finder = parse_qs(urlsplit(str(request.url)).query)["finder"][0]
        if request.url.path.endswith("recruitingCEJobRequisitions"):
            assert "siteNumber=CX_1" in finder
            if "userTargetFacetInputTerm" in finder:
                facets: list[JsonValue] = [{"Id": 7, "Name": "La Canada, CA, United States"}]
                if canada:
                    facets.append({"Id": CANADA, "Name": "Canada", "TotalCount": 3})
                return httpx2.Response(
                    200,
                    json={
                        "items": [
                            {"TotalJobsCount": 4, "requisitionList": [], "locationsFacet": facets}
                        ]
                    },
                )
            assert f"locationId={CANADA}" in finder
            offset = int(finder.split("offset=")[1].split(",")[0])
            rows = [_summary(key, title) for key, (title, _) in POSTINGS.items()]
            page = rows[offset : offset + 2]
            return httpx2.Response(
                200, json={"items": [{"TotalJobsCount": 3, "requisitionList": page}]}
            )
        identifier = finder.split('Id="')[1].split('"')[0]
        details.append(identifier)
        if identifier in withdrawn:
            return httpx2.Response(200, json={"items": []})
        title, job_type = POSTINGS[identifier]
        return httpx2.Response(200, json={"items": [_detail(identifier, title, job_type)]})

    return httpx2.MockTransport(respond)


def test_oracle_canada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(oracle, "PAGE_SIZE", 2)
    details: list[str] = []
    fetched = oracle.fetch_postings(_company(), None, transport=_transport(details))
    assert sorted(details) == ["40892", "40894"]
    assert fetched.payload is not None and not fetched.failures
    scraped = oracle.scrape_postings(_company(), fetched.payload)
    assert scraped.fetched == 3
    assert scraped.listed_urls == (
        f"https://{HOST}/hcmUI/CandidateExperience/en/sites/ExampleCareers/job/40893",
    )
    documents = {document.external_id: document for document in scraped.documents}
    co_op = HeuristicNormalizer().extract(documents["40892"]).jobs[0]
    assert co_op.title == "Embedded Software Co-op/Intern"
    assert co_op.company == "Example Networks"
    assert sorted(co_op.locations) == ["Canada", "Ottawa, Ontario, Canada"]
    assert co_op.is_canada_internship and not co_op.is_toronto_area
    assert co_op.application_url.endswith("/sites/ExampleCareers/job/40892")
    assert co_op.source_job_id == "40892"
    engineer = HeuristicNormalizer().extract(documents["40894"]).jobs[0]
    assert not engineer.is_canada_internship
    description = clean_description(
        documents["40892"].content, source_url=documents["40892"].source_url
    )
    assert description is not None
    assert "Automate lab equipment." in description
    assert "Enrolled in computer engineering." in description
    again = oracle.fetch_postings(_company(), fetched.etag, transport=_transport([]))
    assert again.payload is None
