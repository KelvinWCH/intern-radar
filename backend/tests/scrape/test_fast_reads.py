import json

from job_backend.scrape.pipeline.models import RawDocument
from job_backend.scrape.utils.job_readiness import has_structured_description


def test_fast_path_needs_description() -> None:
    for content in (
        "Loading jobs " * 200,
        '{"@type":"JobPosting","title":"Intern"}',
        '{"@type":"Organization","description":"Company details"}',
    ):
        assert not has_structured_description(
            RawDocument(content=content, source_url="https://example.com/job")
        )
    structured = json.dumps(
        {
            "@graph": [
                {
                    "@type": "JobPosting",
                    "title": "Intern",
                    "description": "Complete qualifications. " * 30,
                }
            ]
        }
    )
    assert has_structured_description(
        RawDocument(
            content="Header\n" + structured + "\nFooter", source_url="https://example.com/job"
        )
    )
