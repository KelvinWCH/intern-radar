import re
from typing import Literal
from urllib.parse import urlsplit

ProfileSite = Literal["linkedin", "github"]

_SITES: dict[ProfileSite, tuple[str, str]] = {
    "linkedin": ("linkedin.com", "https://www.linkedin.com/in/"),
    "github": ("github.com", "https://github.com/"),
}
_HANDLE = re.compile(r"@?([A-Za-z0-9][A-Za-z0-9_-]{0,99})")


def profile_url(site: ProfileSite, text: str) -> str | None:
    text = text.strip()
    host, handle_prefix = _SITES[site]
    if not text or _is_label(site, text):
        return None
    handle = _HANDLE.fullmatch(text)
    if handle:
        return handle_prefix + handle.group(1)
    try:
        parts = urlsplit(text if "://" in text else "https://" + text)
        _ = parts.port
    except ValueError:
        raise ValueError(f"Enter a valid {host} profile URL") from None
    hostname = (parts.hostname or "").casefold()
    path = parts.path.rstrip("/")
    if (
        parts.scheme not in {"http", "https"}
        or not (hostname == host or hostname.endswith("." + host))
        or parts.username
        or parts.password
        or not path.strip("/")
        or re.search(r"[\s\\]", text)
    ):
        raise ValueError(f"Enter a {host} profile URL, such as {handle_prefix}your-name")
    return "https://" + hostname + path


def normalize_profile_url(site: ProfileSite, value: object) -> object:
    return profile_url(site, value) if isinstance(value, str) else value


def normalize_profile_label(value: object) -> object:
    return (" ".join(value.split()) or None) if isinstance(value, str) else value


def profile_label(url: str) -> str:
    parts = urlsplit(url)
    return (parts.hostname or "").removeprefix("www.") + parts.path


def split_profile_links(
    links: list[str], linkedin: str | None, github: str | None
) -> tuple[list[str], str | None, str | None]:
    profiles: dict[ProfileSite, str | None] = {"linkedin": linkedin, "github": github}
    remaining: list[str] = []
    for link in links:
        site = _profile_site(link)
        if site is None:
            remaining.append(link)
            continue
        saved = profiles[site]
        try:
            url = profile_url(site, link)
        except ValueError:
            remaining.append(link)
            continue
        # a github repo link is a project, not the persons profile
        if saved is None and url is not None and (site != "github" or url.count("/") == 3):
            profiles[site] = url
        elif saved is None or (url is not None and profile_label(url) != profile_label(saved)):
            remaining.append(link)
    return remaining, profiles["linkedin"], profiles["github"]


def _is_label(site: ProfileSite, text: str) -> bool:
    return text.casefold() in {site, site + " profile", _SITES[site][0]}


def _profile_site(link: str) -> ProfileSite | None:
    text = link.strip()
    try:
        hostname = urlsplit(text if "://" in text else "https://" + text).hostname or ""
    except ValueError:
        hostname = ""
    for site, (host, _prefix) in _SITES.items():
        if _is_label(site, text) or hostname == host or hostname.endswith("." + host):
            return site
    return None
