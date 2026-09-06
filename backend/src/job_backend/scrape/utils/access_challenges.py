from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from job_backend.scrape.utils.browser_errors import BrowserAccessError
from job_backend.scrape.utils.constants import (
    CHALLENGE_LABEL,
    CHALLENGE_PATH,
    CHALLENGE_QUERY,
)
from job_backend.scrape.utils.pacing import observe_response


def require_no_challenge(
    url: str, labels: tuple[str, ...] = (), *, record_response: bool = True
) -> None:
    parts = urlsplit(url)
    host = (parts.hostname or "").casefold()
    if (
        CHALLENGE_PATH.search(unquote(parts.path))
        or CHALLENGE_QUERY.search(parts.query)
        or host == "captcha-delivery.com"
        or host.endswith(".captcha-delivery.com")
        or any(CHALLENGE_LABEL.fullmatch(" ".join(label.split())) for label in labels)
    ):
        if record_response:
            observe_response(url, 403)
        error = BrowserAccessError(
            "The website returned an access challenge instead of job content"
        )
        error.url = url
        raise error


class _ChallengeLabels(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.labels: list[str] = []
        self.parts: list[str] | None = None
        self.text_labels: list[str] = []
        self.text_parts: list[str] = []
        self.ignored: list[str] = []

    def _flush_text(self) -> None:
        self.text_labels.append("".join(self.text_parts))
        self.text_parts = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "svg", "noscript", "template"}:
            self.ignored.append(tag)
        if self.ignored:
            return
        if tag in {"title", "h1", "h2", "h3", "p", "div", "li", "br", "button"}:
            self._flush_text()
        if tag in {"title", "h1", "h2"}:
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.ignored:
            return
        self.text_parts.append(data)
        if self.parts is not None:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.ignored:
            if tag == self.ignored[-1]:
                self.ignored.pop()
            return
        if tag in {"title", "h1", "h2", "h3", "p", "div", "li", "button"}:
            self._flush_text()
        if tag in {"title", "h1", "h2"} and self.parts is not None:
            self.labels.append("".join(self.parts))
            self.parts = None


def require_readable_response(
    url: str, body: str, *, html: bool, record_response: bool = True
) -> None:
    labels: tuple[str, ...] = ()
    if html:
        parser = _ChallengeLabels()
        parser.feed(body)
        parser.close()
        labels = tuple(parser.labels)
        text_labels = (*parser.text_labels, "".join(parser.text_parts))
        if sum(len(" ".join(label.split())) for label in text_labels) < 4000:
            labels += (
                *text_labels,
                *(line for label in text_labels for line in label.splitlines()),
            )
    elif len(body) < 4000:
        labels = tuple(body.splitlines())
    require_no_challenge(url, labels, record_response=record_response)
