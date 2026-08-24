import hashlib
import random
import time
from collections import Counter
from collections.abc import Callable, Generator
from concurrent.futures import CancelledError
from contextlib import ExitStack, closing, contextmanager
from threading import Lock, Semaphore
from urllib.parse import urlsplit

from job_backend.common.logger import get_logger
from job_backend.persistence.database import Database
from job_backend.persistence.errors import DatabaseUnavailableError
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.lever.urls import posting_urls
from job_backend.scrape.pipeline.cache import ScrapeCache
from job_backend.scrape.pipeline.challenges import ChallengeMemory
from job_backend.scrape.pipeline.heuristics.targeting import listing_is_candidate
from job_backend.scrape.pipeline.models import JobLink, JobPageCache, JobPageSettings, RawDocument
from job_backend.scrape.pipeline.telemetry.performance import (
    PerformanceTracker,
    failure_reason,
    safe_failure_url,
)
from job_backend.scrape.utils.access_challenges import (
    require_no_challenge,
    require_readable_response,
)
from job_backend.scrape.utils.browser_errors import (
    BrowserAccessError,
    BrowserUnavailableError,
)
from job_backend.scrape.utils.job_page_client import open_page_reader
from job_backend.scrape.utils.job_page_http import HttpPageStatusError
from job_backend.scrape.utils.pacing import paced_mode
from job_backend.scrape.utils.pool import ResourcePool
from job_backend.scrape.utils.public_urls import is_linkedin_url
from job_backend.scrape.utils.robots import RobotsDisallowedError

logger = get_logger(__name__)


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _read_description_page(url: str, reader: Callable[[str], RawDocument]) -> RawDocument:
    urls = posting_urls(url)
    page = reader(urls[0] if urls is not None else url)
    final_urls = posting_urls(page.source_url)
    if final_urls is not None and final_urls[0] != page.source_url:
        page = reader(final_urls[0])
    return page


class JobPages:
    def __init__(
        self,
        engine: Database,
        settings: JobPageSettings,
        *,
        fetch_page: Callable[[str], RawDocument] | None = None,
        now: int | None = None,
        require_recent_dates: bool = True,
        links_are_apply_urls: bool = True,
        performance: PerformanceTracker | None = None,
    ) -> None:
        self.engine = engine
        self.settings = settings
        self.fetch_page = fetch_page
        self.now = int(time.time()) if now is None else now
        self.retry_needed = False
        self.deferred = 0
        self.flagged_links: list[JobLink] = []
        self.robots_blocked: set[str] = set()
        self.require_recent_dates = require_recent_dates
        self.links_are_apply_urls = links_are_apply_urls
        self.performance = performance or PerformanceTracker()

    def _eligible(self, links: list[JobLink]) -> list[JobLink]:
        identities: dict[str, str] = {}
        selected: list[JobLink] = []
        visited: set[tuple[str | None, str]] = set()
        cutoff = self.now - self.settings.max_age_days * 86400
        for link in links:
            if link.external_id is not None:
                previous = identities.setdefault(link.external_id, link.url)
                if previous != link.url:
                    raise SourceDataError("Scraper returned conflicting duplicate record IDs")
            if self.require_recent_dates:
                if link.date_posted is not None and not 0 <= link.date_posted <= self.now:
                    continue
                if self.settings.max_age_days and (
                    link.date_posted is None or link.date_posted < cutoff
                ):
                    continue
            identity = (link.external_id, link.url)
            if not listing_is_candidate(link.listing_data):
                continue
            if identity not in visited:
                selected.append(link)
                visited.add(identity)
        return selected

    def select(self, links: list[JobLink]) -> list[JobLink]:
        return [link for link in self._eligible(links) if not is_linkedin_url(link.url)]

    def documents(self, links: list[JobLink]) -> Generator[RawDocument, None, None]:
        eligible = self._eligible(links)
        # linkedin doesnt allow scraping so we never open it, the job just gets flagged
        for link in eligible:
            if is_linkedin_url(link.url):
                self.flagged_links.append(link)
                self.performance.event(
                    f"Saved for manual review without opening LinkedIn: {link.url}"
                )
        selected = [link for link in eligible if not is_linkedin_url(link.url)]
        if not selected:
            return
        url_locks = {link.url: Lock() for link in selected}
        remaining = Counter(link.url for link in selected)
        shared_pages: dict[str, RawDocument] = {}
        hosts = {
            urlsplit(link.url).netloc: Semaphore(self.settings.per_host_concurrency)
            for link in selected
        }
        counter_lock = Lock()
        downloads = 0
        metrics = self.performance
        cache = ScrapeCache(self.engine)
        cache_seconds = self.settings.cache_seconds
        cache_max_seconds = (
            max(cache_seconds, self.settings.cache_max_seconds) if cache_seconds else 0
        )
        challenges = ChallengeMemory(
            cache,
            (_host(link.url) for link in selected),
            now=self.now,
            enabled=paced_mode(),
        )
        challenge_skips: Counter[str] = Counter()
        workers = (
            self.settings.browser_concurrency
            if self.settings.renderer == "browser"
            else self.settings.http_concurrency
        )
        if not self.settings.browser_headless:
            workers = 1
        with ExitStack() as resources:
            browser_settings = self.settings.model_copy(update={"renderer": "browser"})
            browser_pool = resources.enter_context(
                ResourcePool(
                    lambda: open_page_reader(browser_settings, performance=metrics),
                    self.settings.browser_concurrency if workers > 1 else 1,
                )
            )

            def browser_read(url: str) -> RawDocument:
                return browser_pool.submit(url).result()

            @contextmanager
            def reader_factory() -> Generator[Callable[[JobLink], RawDocument | None], None, None]:
                with ExitStack() as local:
                    reader = self.fetch_page

                    def read(link: JobLink) -> RawDocument | None:
                        nonlocal downloads, reader
                        url_hash = hashlib.sha256(link.url.encode()).hexdigest()
                        with url_locks[link.url]:
                            page = shared_pages.get(link.url)
                            if page is None:
                                cached = cache.get(
                                    JobPageCache,
                                    (url_hash, self.settings.cache_key),
                                    ttl_seconds=cache_max_seconds,
                                )
                                page = (
                                    RawDocument(
                                        content=cached.content,
                                        source_url=cached.final_url,
                                        media_type=cached.media_type,
                                        apply_url=cached.apply_url,
                                        date_posted=cached.date_posted,
                                        application_url=cached.application_url,
                                    )
                                    if cached is not None
                                    and self.now - cache_max_seconds < cached.fetched_at <= self.now
                                    else None
                                )
                            if page is not None:
                                try:
                                    require_readable_response(
                                        page.source_url,
                                        page.content,
                                        html="html" in page.media_type,
                                        record_response=False,
                                    )
                                except BrowserAccessError:
                                    page = None
                            if page is not None:
                                metrics.increment("page_cache_hits")
                                metrics.event(f"Using saved copy of {link.url}")
                            else:
                                if challenges.skipped(_host(link.url)) is not None:
                                    with counter_lock:
                                        challenge_skips[_host(link.url)] += 1
                                        self.retry_needed = True
                                    return None
                                first_deferral = False
                                with counter_lock:
                                    capped = downloads >= self.settings.max_downloads_per_scrape
                                    if capped:
                                        self.deferred += 1
                                        self.retry_needed = True
                                        first_deferral = self.deferred == 1
                                    else:
                                        downloads += 1
                                if capped:
                                    if first_deferral:
                                        metrics.record_failure(
                                            "download",
                                            SourceDataError(
                                                "Job-page download limit of "
                                                f"{self.settings.max_downloads_per_scrape} "
                                                "reached; the remaining postings are read on "
                                                "the next run"
                                            ),
                                            level="warning",
                                        )
                                    return None
                                metrics.increment("downloads")
                                metrics.event(f"Downloading {link.url}")
                                if reader is None:
                                    try:
                                        reader = local.enter_context(
                                            open_page_reader(
                                                self.settings,
                                                browser_fallback=browser_read,
                                                performance=metrics,
                                            )
                                        )
                                    except Exception as error:
                                        metrics.increment("page_failures")
                                        metrics.record_failure("download", error, link.url)
                                        raise
                                try:
                                    with (
                                        hosts[urlsplit(link.url).netloc],
                                        metrics.measure("download_seconds"),
                                    ):
                                        require_no_challenge(link.url)
                                        page = _read_description_page(link.url, reader)
                                        require_readable_response(
                                            page.source_url,
                                            page.content,
                                            html="html" in page.media_type,
                                        )
                                except (
                                    BrowserUnavailableError,
                                    CancelledError,
                                    DatabaseUnavailableError,
                                ) as error:
                                    metrics.increment("page_failures")
                                    metrics.record_failure("download", error, link.url)
                                    raise
                                except RobotsDisallowedError as error:
                                    # like LinkedIn: saved from its listing, opened by you
                                    with counter_lock:
                                        self.flagged_links.append(link)
                                        self.robots_blocked.add(link.url)
                                    metrics.event(
                                        "Saved for manual review; robots.txt asks crawlers "
                                        f"not to open {error.url}"
                                    )
                                    return None
                                except Exception as error:
                                    metrics.increment("page_failures")
                                    metrics.record_failure(
                                        "download", error, link.url, level="warning"
                                    )
                                    self.retry_needed = True
                                    if isinstance(error, BrowserAccessError) or (
                                        isinstance(error, HttpPageStatusError)
                                        and error.status in {401, 403}
                                    ):
                                        # the host that showed the check, after redirects
                                        challenges.challenged(_host(error.url or link.url))
                                    if isinstance(error, BrowserAccessError) or (
                                        isinstance(error, HttpPageStatusError)
                                        and error.status in {401, 403, 503}
                                    ):
                                        with counter_lock:
                                            self.flagged_links.append(link)
                                        metrics.event(f"Saved for manual review: {link.url}")
                                    logger.warning(
                                        "Could not read application page %s: %s: %s; continuing",
                                        safe_failure_url(link.url),
                                        type(error).__name__,
                                        failure_reason(error),
                                    )
                                    return None
                                challenges.readable(_host(page.source_url))
                                cache.put(
                                    JobPageCache(
                                        url_hash=url_hash,
                                        renderer_key=self.settings.cache_key,
                                        requested_url=link.url,
                                        final_url=page.source_url,
                                        content=page.content,
                                        media_type=page.media_type,
                                        apply_url=page.apply_url,
                                        date_posted=page.date_posted,
                                        application_url=page.application_url,
                                        fetched_at=self.now,
                                    ),
                                    ttl_seconds=random.uniform(cache_seconds, cache_max_seconds),
                                )
                            remaining[link.url] -= 1
                            if remaining[link.url]:
                                shared_pages[link.url] = page
                            else:
                                shared_pages.pop(link.url, None)
                        page_urls = posting_urls(page.source_url)
                        return RawDocument(
                            content=page.content,
                            source_url=page.source_url,
                            media_type=page.media_type,
                            external_id=link.external_id or ("url:" + url_hash),
                            listing_url=link.listing_url,
                            listing_data=link.listing_data,
                            application_url=page.application_url or page.source_url,
                            apply_url=(
                                page_urls[1]
                                if page_urls is not None
                                else link.url
                                if self.links_are_apply_urls
                                else page.apply_url
                            ),
                            date_posted=link.date_posted
                            if link.date_posted is not None
                            else page.date_posted,
                        )

                    yield read

            pool = resources.enter_context(ResourcePool(reader_factory, workers))
            with closing(pool.map(selected)) as documents:
                for document in documents:
                    if document is not None:
                        yield document
        if self.deferred:
            metrics.event(
                f"Download limit reached: {self.deferred:,} postings wait for the next run",
                "warning",
            )
        for host, count in sorted(challenge_skips.items()):
            record = challenges.skipped(host)
            if record is None:
                continue
            resume = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(record.skip_until))
            metrics.record_failure(
                "download",
                SourceDataError(
                    f"{host} answered {record.streak} runs in a row with a security check; "
                    f"its {count:,} postings are tried again after {resume}"
                ),
                level="warning",
            )
