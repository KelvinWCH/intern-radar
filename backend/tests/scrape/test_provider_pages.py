import pytest

from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.normalizer import HeuristicNormalizer
from job_backend.scrape.pipeline.heuristics.pages import provider_page
from job_backend.scrape.pipeline.models import RawDocument


@pytest.mark.parametrize(
    ("url", "html", "identifier"),
    [
        (
            "https://boards.greenhouse.io/example/jobs/123",
            '<h1 class="app-title">Software Intern</h1><span class="company-name">at Example</span>'
            '<div class="location">Toronto, Canada</div>',
            None,
        ),
        (
            "https://jobs.lever.co/example/123",
            '<div class="posting-headline"><h2>Software Intern</h2>'
            '<div class="posting-categories"><div class="sort-by-time location">'
            'Toronto, Canada</div><div class="department">Engineering</div></div></div>',
            None,
        ),
        (
            "https://example.wd5.myworkdayjobs.com/External/job/123",
            '<h2 data-automation-id="jobPostingHeader">Software Intern</h2>'
            '<dl data-automation-id="locations"><dt>locations</dt><dd>Toronto, Canada</dd></dl>'
            '<dl data-automation-id="requisitionId"><dt>job requisition id</dt>'
            "<dd>REQ-456</dd></dl>",
            "REQ-456",
        ),
    ],
)
def test_provider_detail_layouts(url: str, html: str, identifier: str | None) -> None:
    document = RawDocument(
        content=html,
        source_url=url,
        media_type="text/html",
        external_id="github-row-id",
        listing_data={"company_name": "Example"},
    )
    job = HeuristicNormalizer().extract(document).jobs[0]
    assert job.title == "Software Intern" and job.company == "Example"
    assert job.locations == ["Toronto, Canada"]
    assert job.is_canada_internship and job.is_toronto_area
    assert job.source_job_id == identifier and job.date_posted is None
    assert job.qualifications.required_skills == []
    assert document.content == html


def test_host_substrings_ignored() -> None:
    html = '<h2 data-automation-id="jobPostingHeader">Senior Engineer</h2>'
    for host in ("myworkdayjobs.com.evil.example", "notmyworkdayjobs.com"):
        facts = provider_page(PageMarkup(html), f"https://{host}/job/123")
        assert facts.title is None
