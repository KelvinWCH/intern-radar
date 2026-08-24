import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.urls.append(value)


def application_url(cell: str, listing_url: str) -> str | None:
    parser = _Anchors()
    parser.feed(cell)
    candidates = parser.urls or re.findall(r"\]\(\s*<?(https?://[^\s<>)]*)>?\s*\)", cell)
    for value in candidates:
        url = urljoin(listing_url, unescape(value))
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            continue
        if parts.hostname in {"img.shields.io", "shields.io"}:
            continue
        if parts.path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
            continue
        return url
    return None
