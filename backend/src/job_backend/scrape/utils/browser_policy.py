import os
from collections.abc import Generator
from contextlib import contextmanager

from job_backend.scrape.utils.constants import UNATTENDED_BROWSER_ENV


@contextmanager
def unattended_browser_mode(enabled: bool) -> Generator[None, None, None]:
    if not enabled:
        yield
        return
    previous = {key: os.environ.get(key) for key in UNATTENDED_BROWSER_ENV}
    os.environ.update(UNATTENDED_BROWSER_ENV)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
