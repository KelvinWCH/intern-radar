import re
import string
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from urllib.parse import quote, urljoin, urlsplit

import httpx2

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.utils.constants import (
    IMPORTER_USER_AGENT,
    ROBOTS_CACHE_SECONDS,
    ROBOTS_MAX_BYTES,
    ROBOTS_MAX_REDIRECTS,
    ROBOTS_PRODUCT_TOKEN,
    ROBOTS_TIMEOUT,
    ROBOTS_UNREACHABLE_SECONDS,
)
from job_backend.scrape.utils.pacing import wait_for_request
from job_backend.scrape.utils.public_urls import require_public_url, resolve_host

_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})")
_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")
_PRINTABLE_ASCII = "".join(chr(code) for code in range(0x21, 0x7F))


class RobotsDisallowedError(SourceDataError):
    def __init__(self, url: str) -> None:
        super().__init__("The site's robots.txt asks crawlers not to open this page")
        self.url = url


class RobotsUnreachableError(SourceDataError):
    pass


def _normalize(value: str) -> str:
    # RFC 9309 2.2.2: percent-encode non-ASCII, decode escaped unreserved characters
    encoded = quote(value, safe=_PRINTABLE_ASCII)

    def unescape(match: re.Match[str]) -> str:
        character = chr(int(match.group(1), 16))
        return character if character in _UNRESERVED else "%" + match.group(1).upper()

    return _ESCAPE.sub(unescape, encoded)


@dataclass(frozen=True)
class RobotsRule:
    allow: bool
    pattern: str
    expression: re.Pattern[str]

    @classmethod
    def parse(cls, allow: bool, value: str) -> "RobotsRule":
        pattern = _normalize(value if value.startswith(("/", "*")) else "/" + value)
        anchored = pattern.endswith("$")
        body = pattern[:-1] if anchored else pattern
        expression = "".join(".*" if part == "*" else re.escape(part) for part in body)
        return cls(allow, pattern, re.compile(expression + (r"\Z" if anchored else ""), re.DOTALL))


@dataclass(frozen=True)
class RobotsRules:
    rules: tuple[RobotsRule, ...] = ()

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        target = _normalize((parts.path or "/") + (f"?{parts.query}" if parts.query else ""))
        if target == "/robots.txt":
            return True
        # the longest matching pattern wins, and allow wins a tie
        best: RobotsRule | None = None
        for rule in self.rules:
            if rule.expression.match(target) is None:
                continue
            if (
                best is None
                or len(rule.pattern) > len(best.pattern)
                or (len(rule.pattern) == len(best.pattern) and rule.allow)
            ):
                best = rule
        return best is None or best.allow


def parse_robots(text: str, product: str = ROBOTS_PRODUCT_TOKEN) -> RobotsRules:
    groups: list[tuple[set[str], list[RobotsRule]]] = []
    agents: set[str] = set()
    rules: list[RobotsRule] = []
    reading_rules = False
    for raw in text.removeprefix("﻿").splitlines():
        line = raw.split("#", 1)[0].strip()
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.strip().casefold()
        value = value.strip()
        if key == "user-agent":
            if reading_rules:
                groups.append((agents, rules))
                agents = set[str]()
                rules = []
                reading_rules = False
            agents.add(value.split("/", 1)[0].strip().casefold())
        elif key in {"allow", "disallow"} and agents:
            reading_rules = True
            if value:
                rules.append(RobotsRule.parse(key == "allow", value))
    if agents:
        groups.append((agents, rules))
    # a group naming this crawler replaces the * groups; groups for the same agent combine
    token = product.casefold()
    agent = token if any(token in names for names, _ in groups) else "*"
    return RobotsRules(tuple(rule for names, found in groups if agent in names for rule in found))


def download_robots(
    robots_url: str,
    *,
    transport: httpx2.BaseTransport | None = None,
    resolver: Callable[[str], tuple[str, ...]] = resolve_host,
) -> RobotsRules:
    current = robots_url
    try:
        with httpx2.Client(
            transport=transport,
            timeout=ROBOTS_TIMEOUT,
            follow_redirects=False,
            headers={"User-Agent": IMPORTER_USER_AGENT, "Accept": "text/plain, */*"},
        ) as client:
            for _ in range(ROBOTS_MAX_REDIRECTS + 1):
                require_public_url(current, resolver=resolver)
                wait_for_request(current)
                with client.stream("GET", current) as response:
                    status = response.status_code
                    if status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            return RobotsRules()
                        current = urljoin(current, location)
                        continue
                    # RFC 9309 2.3.1.3: a 4xx means there are no rules
                    if 400 <= status < 500:
                        return RobotsRules()
                    if not response.is_success:
                        raise RobotsUnreachableError(
                            f"robots.txt answered HTTP {status}; the page is skipped this run"
                        )
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) >= ROBOTS_MAX_BYTES:
                            break
                    text = bytes(body[:ROBOTS_MAX_BYTES]).decode("utf-8", errors="replace")
                    return parse_robots(text)
    except httpx2.HTTPError:
        raise RobotsUnreachableError(
            "robots.txt could not be read; the page is skipped this run"
        ) from None
    # RFC 9309 2.3.1.2: past five redirects the file counts as unavailable
    return RobotsRules()


class RobotsCache:
    def __init__(
        self,
        download: Callable[[str], RobotsRules] = download_robots,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.download = download
        self.clock = clock
        self.lock = Lock()
        self.origin_locks: dict[str, Lock] = {}
        self.entries: dict[str, tuple[float, RobotsRules | None]] = {}

    def rules(self, url: str) -> RobotsRules:
        parts = urlsplit(url)
        origin = f"{parts.scheme.casefold()}://{parts.netloc.casefold()}"
        with self.lock:
            origin_lock = self.origin_locks.setdefault(origin, Lock())
        with origin_lock:
            entry = self.entries.get(origin)
            if entry is not None and entry[0] > self.clock():
                if entry[1] is None:
                    raise RobotsUnreachableError(
                        "robots.txt could not be read; the page is skipped this run"
                    )
                return entry[1]
            try:
                found = self.download(origin + "/robots.txt")
            except RobotsUnreachableError:
                self.entries[origin] = (self.clock() + ROBOTS_UNREACHABLE_SECONDS, None)
                raise
            self.entries[origin] = (self.clock() + ROBOTS_CACHE_SECONDS, found)
            return found

    def require_allowed(self, url: str) -> None:
        if not self.rules(url).allows(url):
            raise RobotsDisallowedError(url)


_cache = RobotsCache()


def require_robots_allowed(url: str) -> None:
    _cache.require_allowed(url)
