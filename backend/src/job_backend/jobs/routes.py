import time
from collections.abc import Callable, Iterator
from datetime import date
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query

from job_backend.jobs.browsing import Sort, browse_jobs, job_overview
from job_backend.jobs.details import edit_job_details
from job_backend.jobs.duplicates import job_responses
from job_backend.jobs.link_check import check_saved_job
from job_backend.jobs.models import (
    ApplicationStatus,
    Job,
    JobCreate,
    JobEdit,
    JobOverview,
    JobPage,
    JobResponse,
    JobReview,
    SavedJobDescription,
)
from job_backend.jobs.retry import retry_saved_job
from job_backend.jobs.storage import save_user_job
from job_backend.jobs.user_service import EditConflictError, JobNotFoundError
from job_backend.persistence.models import Filter, ReadQuery
from job_backend.persistence.session import Session
from job_backend.scrape.errors import SourceDataError


def create_router(session_dependency: Callable[..., Iterator[Session]]) -> APIRouter:
    router = APIRouter()

    @router.post("/jobs/{job_id}/retry-scrape", summary="Retry one flagged posting")
    def retry_scrape(
        job_id: str, body: JobReview, session: Annotated[Session, Depends(session_dependency)]
    ) -> JobResponse:
        try:
            return retry_saved_job(session.engine, job_id, body.version)
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except EditConflictError as error:
            raise HTTPException(409, str(error)) from None
        except SourceDataError:
            raise HTTPException(
                502,
                "Could not read this posting. Its saved details and flag are preserved. "
                "You can retry or edit it manually.",
            ) from None

    @router.post("/jobs/{job_id}/check-link", summary="Check whether a posting is still open")
    def check_link(
        job_id: str, session: Annotated[Session, Depends(session_dependency)]
    ) -> JobResponse:
        try:
            return check_saved_job(session.engine, job_id)
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except SourceDataError as error:
            raise HTTPException(400, str(error)) from None

    @router.post("/jobs/{job_id}/review", summary="Mark a flagged job as reviewed")
    def review_job(
        job_id: str, body: JobReview, session: Annotated[Session, Depends(session_dependency)]
    ) -> JobResponse:
        job = session.get(Job, job_id, hydrate=False)
        if job is None:
            raise HTTPException(404, "Job not found")
        if job.details_version != body.version:
            raise HTTPException(409, "Job changed. Reload before marking it reviewed.")
        if job.review_reason is not None:
            job.review_reason = None
            job.details_version += 1
            job.last_changed_at = int(time.time())
        try:
            session.commit()
        except EditConflictError:
            raise HTTPException(409, "Job changed. Reload before marking it reviewed.") from None
        return job_responses(session, [job])[0]

    def set_deleted(session: Session, job_id: str, deleted: bool) -> JobResponse:
        job = session.get(Job, job_id, hydrate=False)
        if job is None:
            raise HTTPException(404, "Job not found")
        job.deleted_at = (job.deleted_at or int(time.time())) if deleted else None
        try:
            session.commit()
        except EditConflictError:
            raise HTTPException(409, "Job changed. Refresh and try again.") from None
        return job_responses(session, [job])[0]

    @router.delete("/jobs/{job_id}", summary="Move a job to deleted jobs")
    def delete_job(
        job_id: str, session: Annotated[Session, Depends(session_dependency)]
    ) -> JobResponse:
        return set_deleted(session, job_id, True)

    @router.post("/jobs/{job_id}/restore", summary="Restore a deleted job")
    def restore_job(
        job_id: str, session: Annotated[Session, Depends(session_dependency)]
    ) -> JobResponse:
        return set_deleted(session, job_id, False)

    @router.patch("/jobs/{job_id}", summary="Correct details of any saved job")
    def edit_job(
        job_id: str, body: JobEdit, session: Annotated[Session, Depends(session_dependency)]
    ) -> JobResponse:
        try:
            job = edit_job_details(session, job_id, body)
            return job_responses(session, [job])[0]
        except JobNotFoundError as error:
            raise HTTPException(404, str(error)) from None
        except EditConflictError as error:
            raise HTTPException(409, str(error)) from None

    @router.post("/jobs", summary="Save a pasted job for later")
    def add_job(
        job: JobCreate, session: Annotated[Session, Depends(session_dependency)]
    ) -> JobResponse:
        return save_user_job(session, job, "user_added")

    @router.get("/jobs", summary="Browse saved jobs")
    def list_jobs(
        session: Annotated[Session, Depends(session_dependency)],
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0, le=10000)] = 0,
        active: bool | None = True,
        toronto_area: bool | None = None,
        first_seen_from: Annotated[int | None, Query(ge=0)] = None,
        first_seen_before: Annotated[int | None, Query(ge=0)] = None,
        posted_from: date | None = None,
        posted_before: date | None = None,
        posted_timezone: Annotated[str, Query(max_length=100)] = "UTC",
        q: Annotated[str, Query(max_length=200)] = "",
        company: Annotated[str, Query(max_length=200)] = "",
        location: Annotated[str, Query(max_length=200)] = "",
        source: str | None = None,
        application_status: ApplicationStatus | None = None,
        tracked: bool = False,
        deleted: bool = False,
        flagged: bool | None = None,
        scope: Literal["eligible", "all"] = "eligible",
        activity: Literal["open", "closed", "all"] | None = None,
        sort: Sort | None = None,
        min_match: Annotated[int | None, Query(ge=0, le=100)] = None,
    ) -> JobPage:
        if (
            first_seen_from is not None
            and first_seen_before is not None
            and first_seen_before <= first_seen_from
        ):
            raise HTTPException(
                status_code=422, detail="first_seen_before must follow first_seen_from"
            )
        if posted_from is not None and posted_before is not None and posted_before <= posted_from:
            raise HTTPException(422, "posted_before must follow posted_from")
        try:
            posted_zone = ZoneInfo(posted_timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise HTTPException(422, "Unknown posted_timezone") from None
        if activity is not None:
            active = None if activity == "all" else activity == "open"
        return browse_jobs(
            session,
            limit=limit,
            offset=offset,
            active=active,
            toronto_area=toronto_area,
            first_seen_from=first_seen_from,
            first_seen_before=first_seen_before,
            posted_from=posted_from,
            posted_before=posted_before,
            posted_timezone=posted_zone.key,
            q=q,
            company=company,
            location=location,
            source=source,
            application_status=application_status,
            tracked=tracked,
            deleted=deleted,
            flagged=flagged,
            scope=scope,
            sort=sort,
            min_match=min_match,
        )

    @router.get("/jobs/overview", summary="Count jobs and application stages")
    def overview(
        session: Annotated[Session, Depends(session_dependency)],
        deleted: bool = False,
        scope: Literal["eligible", "all"] = "all",
    ) -> JobOverview:
        return job_overview(session, deleted=deleted, eligible=scope == "eligible")

    @router.get("/jobs/{job_id}/description", summary="Read one original posting for comparison")
    def description(
        job_id: str, session: Annotated[Session, Depends(session_dependency)]
    ) -> SavedJobDescription:
        rows = session.select(
            ReadQuery("jobs", Filter("id", value=job_id), fields=("raw_description",), source=True),
            limit=1,
            count=False,
        ).items
        if not rows:
            raise HTTPException(404, "Job not found")
        return SavedJobDescription.model_validate(rows[0])

    @router.get("/jobs/{job_id}", summary="Inspect one saved job")
    def get_job(
        job_id: str, session: Annotated[Session, Depends(session_dependency)]
    ) -> JobResponse:
        job = session.get(Job, job_id, hydrate=False)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job_responses(session, [job])[0]

    return router
