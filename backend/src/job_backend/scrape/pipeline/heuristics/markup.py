from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from job_backend.scrape.pipeline.heuristics.models import PageSelector

BLOCK_TAGS = frozenset({"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"})


@dataclass
class PageElement:
    tag: str
    attributes: dict[str, str | None]
    parent: "PageElement | None"
    parts: list[str] = field(default_factory=list[str])

    @property
    def text(self) -> str:
        return " ".join(" ".join(self.parts).split())


class PageMarkup(HTMLParser):
    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[PageElement] = []
        self.stack: list[PageElement] = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = PageElement(tag, dict(attrs), self.stack[-1] if self.stack else None)
        self.elements.append(element)
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        for element in reversed(self.stack):
            element.parts.append(data)
            if element.tag in {"script", "style", "template", "noscript"}:
                break

    def select(self, selector: PageSelector) -> list[PageElement]:
        matches: list[PageElement] = []
        for element in self.elements:
            if selector.tag is not None and element.tag != selector.tag:
                continue
            if selector.attribute is not None:
                value = element.attributes.get(selector.attribute)
                if selector.attribute == "class":
                    tokens = (value or "").split()
                    if not any(
                        token.startswith(selector.value or "")
                        if selector.prefix
                        else token == selector.value
                        for token in tokens
                    ):
                        continue
                elif selector.prefix:
                    if value is None or not value.startswith(selector.value or ""):
                        continue
                elif value != selector.value:
                    continue
            parent: PageElement | None = element
            ancestor_matches = selector.ancestor_class is None
            hidden = False
            while parent is not None:
                if "hidden" in parent.attributes or parent.attributes.get("aria-hidden") == "true":
                    hidden = True
                if (
                    selector.excluded_ancestor_id
                    and parent.attributes.get("id") == selector.excluded_ancestor_id
                ):
                    hidden = True
                if selector.ancestor_class in (parent.attributes.get("class") or "").split():
                    ancestor_matches = True
                parent = parent.parent
            if ancestor_matches and not hidden:
                matches.append(element)
        return matches

    def first_text(self, selectors: tuple[PageSelector, ...]) -> str | None:
        for selector in selectors:
            values = list(dict.fromkeys(node.text for node in self.select(selector) if node.text))
            if len(values) == 1:
                return values[0]
        return None

    def texts(self, selectors: tuple[PageSelector, ...]) -> list[str]:
        for selector in selectors:
            values = list(dict.fromkeys(node.text for node in self.select(selector) if node.text))
            if values:
                return values
        return []

    def link(self, selectors: tuple[PageSelector, ...], source_url: str) -> str | None:
        for selector in selectors:
            for element in self.select(selector):
                href = element.attributes.get("href")
                if not href or href.startswith("#"):
                    continue
                destination = urljoin(source_url, href)
                parsed = urlsplit(destination)
                if parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username:
                    return destination
        return None

    def paragraphs(self, root: PageElement) -> str:
        blocks: list[str] = []
        for element in self.elements:
            if element.tag not in BLOCK_TAGS or not element.text:
                continue
            parent = element.parent
            nested = False
            while parent is not None and parent is not root:
                nested = nested or parent.tag in BLOCK_TAGS
                parent = parent.parent
            if parent is root and not nested:
                blocks.append(("- " if element.tag == "li" else "") + element.text)
        joined = "\n\n".join(blocks)
        return joined if len(joined) >= 0.8 * len(root.text) else root.text
