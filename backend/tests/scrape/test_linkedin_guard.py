import httpx2
import pytest

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.utils.pacing import pace_request, track_response


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/1",
        "https://lnkd.in/abc",
        "https://media.licdn.com/logo.png",
    ],
)
def test_paced_requests_refuse_linkedin(url: str) -> None:
    with pytest.raises(SourceDataError, match="LinkedIn is blocked"):
        pace_request(httpx2.Request("GET", url))


def test_other_hosts_are_paced_normally() -> None:
    pace_request(httpx2.Request("GET", "https://boards-api.greenhouse.io/v1/boards/x/jobs"))


def test_client_stops_linkedin_redirect() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(str(request.url))
        return httpx2.Response(
            302, headers={"Location": "https://www.linkedin.com/jobs/view/1"}, request=request
        )

    with (
        httpx2.Client(
            transport=httpx2.MockTransport(handler),
            follow_redirects=True,
            event_hooks={"request": [pace_request], "response": [track_response]},
        ) as client,
        pytest.raises(SourceDataError, match="LinkedIn is blocked"),
    ):
        client.get("https://example.com/apply")
    assert seen == ["https://example.com/apply"]
