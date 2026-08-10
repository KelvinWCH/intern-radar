from unittest.mock import patch

from job_backend.persistence.database import Database
from job_backend.persistence.pagination import history_page
from job_backend.persistence.session import Session
from job_backend.scrape.models import ScrapeRun


def test_cursor_pages(engine: Database) -> None:
    with Session(engine) as session, session.begin():
        for index in range(251):
            session.add(ScrapeRun(id=f"run-{index:04}", started_at=100.25, source="fixture"))
    cursor, offset = "", 0
    observed: list[str] = []
    with patch.object(engine.gateway, "find", side_effect=AssertionError("Unbounded scan")):
        while True:
            with Session(engine, read_only=True) as session:
                page, following = history_page(
                    session,
                    ScrapeRun,
                    "started_at",
                    limit=20,
                    offset=offset,
                    cursor=cursor,
                    equal={},
                )
            assert len(page) <= 20
            observed.extend(row.id for row in page)
            if offset == 0:
                row = ScrapeRun(id="newest", started_at=101, source="fixture")
                engine.gateway.commit(
                    {("import_runs", row.id): None}, {("import_runs", row.id): row.to_document()}
                )
            if following is None:
                break
            cursor, offset = following, offset + 20
    assert observed == [f"run-{index:04}" for index in reversed(range(251))]
