import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from job_backend.scrape.lever.urls import posting_urls

WORKDAY_HOST_SUFFIX = ".myworkdayjobs.com"
_WORKDAY_LOCALE = re.compile(r"^/[a-z]{2}-[a-z]{2}(?=/|$)", re.IGNORECASE)
_WORKDAY_REQUISITION = re.compile(r"_([A-Za-z]*-?\d[A-Za-z0-9-]*)$")
_TRACKING_KEYS = {"ref", "referrer", "source", "src", "trackingid", "gh_src"}


def workday_tenant(url: str) -> str | None:
    hostname = (urlsplit(url).hostname or "").lower()
    if not hostname.endswith(WORKDAY_HOST_SUFFIX):
        return None
    tenant = hostname.removesuffix(WORKDAY_HOST_SUFFIX).split(".")[0]
    return tenant or None


def workday_requisition(url: str) -> str | None:
    if workday_tenant(url) is None:
        return None
    segments = [segment for segment in urlsplit(url).path.split("/") if segment]
    if not segments:
        return None
    found = _WORKDAY_REQUISITION.search(segments[-1])
    return found.group(1).upper() if found else None


def canonical_job_url(url: str) -> str:
    lever_urls = posting_urls(url)
    parts = urlsplit(lever_urls[0] if lever_urls is not None else url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    ]
    path = parts.path.rstrip("/") or "/"
    hostname = (parts.hostname or "").lower()
    if hostname in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
        hostname = "job-boards.greenhouse.io"
        if path.endswith("/application"):
            path = path.removesuffix("/application")
    if hostname.endswith(WORKDAY_HOST_SUFFIX):
        path = _WORKDAY_LOCALE.sub("", path).lower() or "/"
    fragment = "" if parts.fragment.lower() in {"apply", "application"} else parts.fragment
    authority = hostname + (
        f":{parts.port}"
        if parts.port is not None and parts.port != (443 if parts.scheme == "https" else 80)
        else ""
    )
    return urlunsplit((parts.scheme.lower(), authority, path, urlencode(sorted(query)), fragment))
