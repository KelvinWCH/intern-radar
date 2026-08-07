import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.utils.constants import LINKEDIN_DOMAINS


def resolve_host(hostname: str) -> tuple[str, ...]:
    try:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        addresses = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    return tuple({str(item[4][0]) for item in addresses})


def is_linkedin_url(url: str) -> bool:
    hostname = (urlsplit(url).hostname or "").rstrip(".")
    return any(hostname == domain or hostname.endswith("." + domain) for domain in LINKEDIN_DOMAINS)


def require_public_url(
    url: str, *, resolver: Callable[[str], tuple[str, ...]] = resolve_host
) -> None:
    parts = urlsplit(url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise SourceDataError("Job pages require a public HTTP URL without credentials")
    # checked on every request and redirect, not just the first link
    if is_linkedin_url(url):
        raise SourceDataError("LinkedIn is blocked; its pages are never requested")
    try:
        addresses = resolver(parts.hostname)
        public = bool(addresses) and all(
            ipaddress.ip_address(value).is_global for value in addresses
        )
    except (OSError, ValueError):
        raise SourceDataError(
            f"Job page hostname could not be validated: {parts.hostname}"
        ) from None
    if not public:
        raise SourceDataError("Job page points to a non-public network address")
