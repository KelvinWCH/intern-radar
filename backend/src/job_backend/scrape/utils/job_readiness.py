from pydantic import JsonValue

from job_backend.scrape.pipeline.heuristics.markup import PageMarkup
from job_backend.scrape.pipeline.heuristics.pages import provider_page
from job_backend.scrape.pipeline.heuristics.structured import structured_record
from job_backend.scrape.pipeline.models import RawDocument
from job_backend.scrape.utils.browser import require_open_page
from job_backend.scrape.utils.page_text import page_text


def _posting(value: JsonValue) -> bool:
    if isinstance(value, list):
        return any(_posting(item) for item in value)
    if not isinstance(value, dict):
        return False
    kind = value.get("@type")
    description = value.get("description")
    if (kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind)) and isinstance(
        description, str
    ):
        return len(description.strip()) >= 200 and isinstance(value.get("title"), str)
    graph = value.get("@graph")
    return _posting(graph) if graph is not None else False


def has_structured_description(document: RawDocument) -> bool:
    markup = PageMarkup(document.content) if "html" in document.media_type else None
    readable = page_text(document.content) if markup is not None else document.content
    lines = readable.splitlines()
    require_open_page(document.source_url, lines[0] if lines else "", tuple(lines[:30]))
    if _posting(structured_record(document, markup)):
        return True
    if markup is not None:
        facts = provider_page(markup, document.source_url)
        return bool(facts.title and facts.description and len(facts.description.strip()) >= 200)
    return False
