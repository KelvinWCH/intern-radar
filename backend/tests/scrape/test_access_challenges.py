import pytest

from job_backend.scrape.utils.access_challenges import require_readable_response
from job_backend.scrape.utils.browser import require_open_page
from job_backend.scrape.utils.browser_errors import BrowserAccessError


@pytest.mark.parametrize(
    "body",
    [
        "<h1>Security verification intern</h1><p>Build secure verification services.</p>",
        "<h1>Security engineer</h1><p>Design a flow with one quick security check.</p>",
        '<h1>Intern</h1><script>const message = "One quick security check";</script>',
    ],
)
def test_security_jobs_readable(body: str) -> None:
    require_readable_response("https://example.com/jobs/security-intern", body, html=True)


def _verification_page(body_text: str) -> str:
    return (
        "<html><head><title>User Verification</title></head><body>"
        "<nav>Search Top Employers Post Jobs</nav>"
        "<h2>We hate to have to ask this, but...</h2>"
        '<p class="first-paragraph">... are you a human?</p>'
        '<form action="/sandbox"><button>Continue</button></form>'
        f"<p>{body_text}</p></body></html>"
    )


@pytest.mark.parametrize("body_text", ["", "Terms of Service and job search tips. " * 200])
def test_verification_pages(body_text: str) -> None:
    url = "https://jobs.example.com/sandbox?destination=%2Fjobs%2Fexample"
    with pytest.raises(BrowserAccessError):
        require_readable_response(url, _verification_page(body_text), html=True)
    for title in ("User Verification", "User Verification | example.com"):
        with pytest.raises(BrowserAccessError):
            require_open_page(url, title)
    with pytest.raises(BrowserAccessError):
        require_readable_response(url, "... are you a human?", html=False)
