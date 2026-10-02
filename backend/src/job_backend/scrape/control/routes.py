from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from job_backend.common.models import AiSettings
from job_backend.persistence.database import Database
from job_backend.persistence.models import Filter, Junction, Order, ReadQuery
from job_backend.persistence.pagination import projected_history_page
from job_backend.persistence.projections import READ_FIELDS
from job_backend.persistence.session import Session
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.scrape.control.activity import scrape_activity
from job_backend.scrape.control.catalog import list_sources
from job_backend.scrape.control.models import (
    ScrapeActivity,
    ScrapeHistoryPage,
    ScrapeRequest,
    ScrapeSource,
    ScrapeTask,
    ScrapeTaskResponse,
)
from job_backend.scrape.control.service import ScrapeBusyError, ScrapeController, task_response
from job_backend.scrape.models import ScrapeRun
from job_backend.scrape.pipeline.models import ScrapeRunResponse, ScrapeRunStatus
from job_backend.scrape.worker.control import cancel_scheduled_scrape


def create_router(engine: Database, controller: ScrapeController) -> APIRouter:
    router = APIRouter(prefix="/scrapes", tags=["scrapes"])

    @router.get("/sources", summary="List available scrape adapters")
    def sources() -> list[ScrapeSource]:
        return list_sources()

    @router.get("/activity", summary="Read live manual, scheduled, and CLI scrape activity")
    def activity() -> ScrapeActivity:
        return scrape_activity(engine)

    @router.post(
        "/scheduled/{identifier}/cancel", summary="Stop the current scheduled scrape batch"
    )
    def cancel_scheduled(identifier: UUID) -> ScrapeActivity:
        try:
            cancel_scheduled_scrape(engine.local_path, str(identifier))
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        return scrape_activity(engine)

    @router.get("/history", summary="Browse detailed per-source import history")
    def history(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
        source: str | None = None,
        status: ScrapeRunStatus | None = None,
        cursor: Annotated[str | None, Query(max_length=1024)] = None,
    ) -> ScrapeHistoryPage:
        if cursor is None and offset > 200:
            raise HTTPException(422, "Use cursor pagination for deeper history")
        with Session(engine, read_only=True) as session:
            if cursor is not None:
                try:
                    page, following = projected_history_page(
                        session,
                        ScrapeRun,
                        "started_at",
                        limit=limit,
                        offset=offset,
                        cursor=cursor,
                        source_fields=(*READ_FIELDS["import_runs"], "performance"),
                        equal={
                            **({"source": source} if source else {}),
                            **({"status": status} if status else {}),
                        },
                    )
                except ValueError as error:
                    raise HTTPException(422, str(error)) from None
                return ScrapeHistoryPage(
                    items=[ScrapeRunResponse.model_validate(row) for row in page],
                    total=None,
                    limit=limit,
                    offset=offset,
                    next_cursor=following,
                )
            page = session.select(
                ReadQuery(
                    "import_runs",
                    Junction(
                        tuple(
                            Filter(field, value=value)
                            for field, value in (("source", source), ("status", status))
                            if value is not None
                        )
                    ),
                    (
                        Order("started_at", descending=True, numeric=True),
                        Order("@key", descending=True),
                    ),
                    fields=(*READ_FIELDS["import_runs"], "performance"),
                    source=True,
                ),
                limit=limit,
                offset=offset,
            )
            return ScrapeHistoryPage(
                items=[ScrapeRunResponse.model_validate(row) for row in page.items],
                total=page.total,
                limit=limit,
                offset=offset,
            )

    @router.get("", summary="Read recent user-requested scrapes")
    def tasks() -> list[ScrapeTaskResponse]:
        with Session(engine, read_only=True) as session:
            tasks = session.recent(ScrapeTask, "created_at", limit=20)
            runs = sorted(
                session.match_any(ScrapeRun, "task_id", {task.id for task in tasks}),
                key=lambda run: (run.started_at, run.id),
            )
            return [
                task_response(session, task, runs=[run for run in runs if run.task_id == task.id])
                for task in tasks
            ]

    @router.post("", status_code=202, summary="Start a bounded background scrape")
    def start(
        request: ScrapeRequest, _settings: Annotated[AiSettings, Depends(resume_ai_settings)]
    ) -> ScrapeTaskResponse:
        try:
            return controller.start(request)
        except ScrapeBusyError as error:
            raise HTTPException(409, str(error)) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @router.get("/{task_id}", summary="Inspect one scrape and its source outcomes")
    def get_task(task_id: str) -> ScrapeTaskResponse:
        with Session(engine, read_only=True) as session:
            task = session.get(ScrapeTask, task_id)
            if task is None:
                raise HTTPException(404, "Scrape not found")
            return task_response(session, task, events=True)

    @router.post("/{task_id}/cancel", summary="Request cancellation of a running scrape")
    def cancel(task_id: str) -> ScrapeTaskResponse:
        with Session(engine) as session, session.begin():
            task = session.get(ScrapeTask, task_id)
            if task is None:
                raise HTTPException(404, "Scrape not found")
            if task.status in {"queued", "running"}:
                task.cancel_requested = True
            return task_response(session, task, events=True)

    return router
