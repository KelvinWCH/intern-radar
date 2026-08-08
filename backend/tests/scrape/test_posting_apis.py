from collections.abc import Callable

import httpx2
import pytest
from pydantic import JsonValue

from job_backend.scrape.pipeline.heuristics.normalizer import HeuristicNormalizer
from job_backend.scrape.pipeline.models import JobPageSettings, RawDocument
from job_backend.scrape.utils.posting_apis import read_posting_api


def _read(
    url: str, respond: Callable[[httpx2.Request], httpx2.Response]
) -> tuple[RawDocument | None, list[str]]:
    requested: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requested.append(str(request.url))
        return respond(request)

    with httpx2.Client(transport=httpx2.MockTransport(handler)) as client:
        document = read_posting_api(
            url, client=client, settings=JobPageSettings(), resolver=lambda _host: ("1.1.1.1",)
        )
    return document, requested


def _workday_detail() -> dict[str, JsonValue]:
    return {
        "jobPostingInfo": {
            "id": "abc123",
            "title": "Software Engineering Intern",
            "jobDescription": "<p>Build tools with Python.</p>",
            "jobReqId": "R_1506084",
            "location": "Toronto, Ontario",
            "country": {"descriptor": "Canada"},
            "startDate": "2026-10-23",
            "externalUrl": "https://td.wd3.myworkdayjobs.com/TD_Bank_Careers/job/Toronto/Intern_R_1506084",
        },
        "hiringOrganization": {"name": "The Toronto-Dominion Bank (Canada)"},
    }


def test_workday_public_record() -> None:
    url = (
        "https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers/job/Toronto/Intern_R_1506084"
        "?utm_source=Simplify"
    )
    document, requested = _read(url, lambda _request: httpx2.Response(200, json=_workday_detail()))
    assert requested == [
        "https://td.wd3.myworkdayjobs.com/wday/cxs/td/TD_Bank_Careers/job/Toronto/Intern_R_1506084"
    ]
    assert document is not None and document.media_type == "application/json"
    assert document.application_url == (
        "https://td.wd3.myworkdayjobs.com/TD_Bank_Careers/job/Toronto/Intern_R_1506084"
    )
    job = HeuristicNormalizer().extract(document).jobs[0]
    assert job.title == "Software Engineering Intern"
    assert job.company == "The Toronto-Dominion Bank (Canada)"
    assert job.locations == ["Toronto, Ontario, Canada"]
    assert job.is_canada_internship and job.is_toronto_area
    assert job.application_url == document.application_url
    assert job.source_job_id == "R_1506084"


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(500, text="Server error"),
        httpx2.Response(200, text="<html>Sign in</html>"),
        httpx2.Response(200, json={"jobPostingInfo": {"title": "Missing description"}}),
    ],
)
def test_falls_back_to_page(response: httpx2.Response) -> None:
    url = "https://td.wd3.myworkdayjobs.com/TD_Bank_Careers/job/Toronto/Intern_R_1"
    document, requested = _read(url, lambda _request: response)
    assert document is None and len(requested) == 1
