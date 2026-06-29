from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from job_backend.scrape.errors import SourceDataError


class _PageText(HTMLParser):
    def __init__(self, base_url: str | None, *, include_structured: bool = True) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored: list[str] = []
        self.base_url = base_url
        self.include_structured = include_structured
        self.links: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        structured = (
            self.include_structured
            and tag == "script"
            and attributes.get("type") == "application/ld+json"
        )
        if tag in {"script", "style", "svg", "noscript", "template"} and not structured:
            self.ignored.append(tag)
        elif not self.ignored and tag == "meta":
            name = attributes.get("name") or attributes.get("property")
            content = attributes.get("content")
            if name in {"description", "og:description", "og:title"} and content:
                self.parts.append(content)
        elif not self.ignored and tag == "a" and self.base_url is not None:
            href = attributes.get("href")
            url = urljoin(self.base_url, href) if href else None
            self.links.append(
                url if url is not None and urlsplit(url).scheme in {"http", "https"} else None
            )

    def handle_endtag(self, tag: str) -> None:
        if self.ignored and tag == self.ignored[-1]:
            self.ignored.pop()
        elif not self.ignored and tag == "a" and self.links:
            url = self.links.pop()
            if url is not None:
                self.parts.append("Link: " + url)

    def handle_data(self, data: str) -> None:
        if not self.ignored and data.strip():
            self.parts.append(data.strip())


def page_text(html: str, *, base_url: str | None = None, include_structured: bool = True) -> str:
    parser = _PageText(base_url, include_structured=include_structured)
    parser.feed(html)
    content = "\n".join(parser.parts).strip()
    if not content:
        raise SourceDataError("Application page contains no readable job content")
    return content
