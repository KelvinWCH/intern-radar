from collections import Counter
from pathlib import Path
from uuid import uuid4

from job_backend.scrape.control.catalog import build_scrape_command, list_sources
from job_backend.scrape.control.models import ScrapeRequest


def test_select_all_sources(tmp_path: Path) -> None:
    sources = [source for source in list_sources() if source.enabled]
    request = ScrapeRequest(request_id=str(uuid4()), sources=[source.id for source in sources])
    command = build_scrape_command(request, tmp_path)
    counts = Counter(source.group for source in sources)
    assert command.count("--repo") == counts["github"]
    assert command.count("--company") == counts["company"]
    assert "--use-ai" not in command
