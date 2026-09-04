from urllib.parse import urlsplit, urlunsplit
from uuid import UUID


def posting_urls(url: str) -> tuple[str, str] | None:
    parts = urlsplit(url)
    segments = parts.path.strip("/").split("/")
    if (
        parts.scheme not in {"http", "https"}
        or parts.hostname not in {"jobs.lever.co", "jobs.eu.lever.co"}
        or parts.username is not None
        or parts.password is not None
        or len(segments) not in {2, 3}
        or (len(segments) == 3 and segments[2] != "apply")
    ):
        return None
    try:
        UUID(segments[1])
    except ValueError:
        return None
    path = "/" + "/".join(segments[:2])
    return (
        urlunsplit((parts.scheme, parts.netloc, path, parts.query, "")),
        urlunsplit((parts.scheme, parts.netloc, path + "/apply", parts.query, "")),
    )
