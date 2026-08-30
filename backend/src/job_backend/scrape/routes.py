from collections.abc import Callable, Iterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from job_backend.persistence.models import Filter, Junction, ReadQuery
from job_backend.persistence.session import Session
from job_backend.scrape.models import ScrapeSummary


def create_router(session_dependency: Callable[..., Iterator[Session]]) -> APIRouter:
    router = APIRouter()

    @router.get("/import-runs/summary", summary="Summarize daily scrape activity")
    def scrape_summary(
        session: Annotated[Session, Depends(session_dependency)],
        from_timestamp: Annotated[int, Query(ge=0)],
        before_timestamp: Annotated[int, Query(ge=0)],
    ) -> ScrapeSummary:
        if before_timestamp <= from_timestamp:
            raise HTTPException(
                status_code=422, detail="before_timestamp must follow from_timestamp"
            )
        selected = Junction(
            (
                Junction(
                    (
                        Filter("finished_at", "ge", from_timestamp),
                        Filter("finished_at", "lt", before_timestamp),
                    )
                ),
                Junction(
                    (
                        Filter("status", value="running"),
                        Filter("started_at", "ge", from_timestamp),
                        Filter("started_at", "lt", before_timestamp),
                    )
                ),
            ),
            "or",
        )
        groups = session.groups(
            ReadQuery("import_runs", selected),
            ("status",),
            (
                "created",
                "unchanged",
                "updated",
                "input_tokens",
                "output_tokens",
                "@elapsed",
            ),
        )
        values: dict[str, float] = {}
        for row in groups:
            for field in (
                "created",
                "unchanged",
                "updated",
                "input_tokens",
                "output_tokens",
                "@elapsed",
                "count",
            ):
                number = row.get(field)
                if isinstance(number, int | float):
                    if (
                        field not in {"created", "unchanged", "updated"}
                        or row["status"] == "completed"
                    ):
                        values[field] = values.get(field, 0) + number
            count = row["count"]
            if isinstance(count, int):
                values[str(row["status"])] = count
        return ScrapeSummary(
            created=int(values.get("created", 0)),
            duplicates=int(values.get("unchanged", 0)),
            updated=int(values.get("updated", 0)),
            runs=int(values.get("count", 0)),
            failed_runs=int(values.get("failed", 0)),
            running_runs=int(values.get("running", 0)),
            input_tokens=int(values.get("input_tokens", 0)),
            output_tokens=int(values.get("output_tokens", 0)),
            scrape_seconds=int(values.get("@elapsed", 0)),
        )

    return router
