import re
from urllib.parse import quote

import httpx2

from job_backend.scrape.pipeline.models import FetchResult
from job_backend.scrape.utils.http import download_feed


def raw_file_url(repository: str, branch: str, path: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Use a GitHub repository in owner/name format")
    if not branch or not path or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("Provide a branch and a relative file path without parent directories")
    return (
        "https://raw.githubusercontent.com/"
        + repository
        + "/"
        + quote(branch, safe="")
        + "/"
        + quote(path, safe="/")
    )


def download_file(
    repository: str,
    branch: str,
    path: str,
    etag: str | None,
    *,
    transport: httpx2.BaseTransport | None = None,
) -> FetchResult:
    return download_feed(raw_file_url(repository, branch, path), etag, transport=transport)
