from collections.abc import Callable
from urllib.parse import urljoin

import httpx2

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.models import JobPageSettings, RawDocument
from job_backend.scrape.utils.access_challenges import require_readable_response
from job_backend.scrape.utils.page_text import page_text
from job_backend.scrape.utils.public_urls import require_public_url, resolve_host
from job_backend.scrape.utils.robots import require_robots_allowed


class HttpPageStatusError(SourceDataError):
    def __init__(self, status: int, url: str | None = None) -> None:
        self.status = status
        self.url = url
        super().__init__(f"Job page returned HTTP {status}")


def fetch_http_page(
    url: str,
    *,
    client: httpx2.Client,
    settings: JobPageSettings,
    resolver: Callable[[str], tuple[str, ...]] = resolve_host,
) -> RawDocument:
    current = url
    try:
        for _ in range(6):
            require_public_url(current, resolver=resolver)
            # checked on every redirect, like the public address check
            require_robots_allowed(current)
            with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    destination = response.headers.get("location")
                    if not destination:
                        raise SourceDataError("Job-page redirect has no destination")
                    current = urljoin(current, destination)
                    continue
                if not response.is_success:
                    if response.status_code not in {401, 403, 503}:
                        raise HttpPageStatusError(response.status_code, current)
                media_type = response.headers.get("content-type", "text/html").split(";", 1)[0]
                if not media_type.startswith("text/") and media_type not in {
                    "application/xhtml+xml",
                    "application/json",
                    "application/ld+json",
                }:
                    if not response.is_success:
                        raise HttpPageStatusError(response.status_code, current)
                    raise SourceDataError("Application link did not return an HTML or text page")
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > settings.max_page_bytes:
                        if not response.is_success:
                            raise HttpPageStatusError(response.status_code, current)
                        raise SourceDataError("Job page exceeds JOB_PAGE_MAX_BYTES")
                    chunks.append(chunk)
                body = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                require_readable_response(current, body, html="html" in media_type)
                try:
                    content = (
                        page_text(body, base_url=current if settings.include_links else None)
                        if "html" in media_type
                        else body.strip()
                    )
                except SourceDataError:
                    if not response.is_success:
                        raise HttpPageStatusError(response.status_code, current) from None
                    raise
                require_readable_response(current, content, html=False)
                if not response.is_success:
                    raise HttpPageStatusError(response.status_code, current)
                if not content:
                    raise SourceDataError("Application page is empty")
                return RawDocument(content=body, source_url=current, media_type=media_type)
    except httpx2.HTTPError:
        raise SourceDataError("Job-page request failed; check connectivity or timeout") from None
    raise SourceDataError("Application link exceeded the five-redirect limit")
