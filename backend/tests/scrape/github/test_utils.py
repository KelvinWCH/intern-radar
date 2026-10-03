import httpx2
import pytest

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.github.utils.download import download_file
from job_backend.scrape.github.utils.markdown_links import (
    collect_company_links,
    collect_markdown_links,
)


def test_conditional_download() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "https://raw.githubusercontent.com/example/jobs/main/README.md"
        assert request.headers["If-None-Match"] == '"version"'
        return httpx2.Response(304)

    result = download_file(
        "example/jobs", "main", "README.md", '"version"', transport=httpx2.MockTransport(handler)
    )
    assert result.payload is None and result.etag == '"version"'


def test_markdown_rows() -> None:
    markdown = b"""# Internships
| Section | Count |
|--|--:|
| Navigation | 3 |
| Company | Role | Apply | Date Posted |
|---|---|:--:|---|
| Example | Intern | <a href="https://example.com/one">Apply</a> | Oct 17, 2026 |
| \xe2\x86\xb3 | Intern | [![Apply](https://e.co/a.svg)](https://example.com/two) | Oct 16, 2026 |
| Second | Intern | Closed | Oct 15, 2026 |
"""
    result = collect_markdown_links(
        markdown, "https://example.com/README.md", required_columns=("Company", "Role")
    )
    assert result.fetched == 3 and len(result.links) == 2
    assert [link.url for link in result.links] == [
        "https://example.com/one",
        "https://example.com/two",
    ]
    assert result.documents == []
    assert all(link.date_posted is not None for link in result.links)


@pytest.mark.parametrize("kind", ["table", "sections"])
def test_layout_change_fails(kind: str) -> None:
    collector = collect_markdown_links if kind == "table" else collect_company_links
    with pytest.raises(SourceDataError, match="format may have changed"):
        collector(b"404: Not Found", "https://example.com/README.md")
