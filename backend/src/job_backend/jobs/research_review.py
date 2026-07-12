import time

from pydantic import JsonValue, TypeAdapter

from job_backend.common.models import AiModelOptions, AiSettings
from job_backend.jobs.document_response import document_response
from job_backend.jobs.models import (
    DocumentDetail,
    JobDocument,
    JobUserRecord,
    PreparedTailoring,
    TailoringJob,
    TailorRequest,
)
from job_backend.jobs.user_service import EditConflictError, JobNotFoundError
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.profile.models import UserProfile
from job_backend.resumes.models import ResearchReport, ResearchReview, TailoringEvent
from job_backend.resumes.research.analyze import validate_research
from job_backend.resumes.research.generic import generic_research_prompt


def review_research(
    engine: Database, document_id: str, review: ResearchReview, settings: AiSettings
) -> PreparedTailoring | DocumentDetail:
    now = int(time.time())
    json_object = TypeAdapter(dict[str, JsonValue])
    with Session(engine) as session, session.begin():
        row = session.get(JobDocument, document_id)
        if row is None:
            raise JobNotFoundError("Document not found")
        legacy_failure = (
            row.status == "failed"
            and "Research citation does not belong to its stated source" in (row.error or "")
            and not row.has_resume
            and not row.has_cover_letter
        )
        if (
            row.research is None
            or row.review is not None
            or (row.status != "awaiting_review" and not legacy_failure)
        ):
            raise EditConflictError("This attempt is not waiting for research review.")
        research = ResearchReport.model_validate(row.research)
        if research.revision != review.revision:
            raise EditConflictError("This report changed. Reload it before continuing.")
        if review.analysis is not None and review.action != "generate_generic":
            research.analysis = review.analysis
        research.approved_at = None
        validate_research(research)
        research.revision += 1
        if review.action == "continue":
            research.approved_at = now
        row.research = json_object.validate_python(research.model_dump(mode="json"))
        row.status = "awaiting_review"
        row.error = None
        row.finished_at = None
        for stage in row.stages:
            if stage.get("key") == "research":
                stage.update(status="awaiting_review", message="Research ready for your review")
            elif stage.get("message") != "Not selected":
                stage.update(status="queued", message="Waiting for research approval")
        message = (
            "Generating a generic company and role report"
            if review.action == "generate_generic"
            else "Research approved, continuing with the saved inputs"
            if review.action == "continue"
            else "Research edits saved. Check the citation results before continuing"
        )
        row.events.append(
            json_object.validate_python(
                TailoringEvent(
                    id=len(row.events) + 1, created_at=now, stage="validate", message=message
                ).model_dump(mode="json")
            )
        )
        if review.action == "save":
            session.flush()
            return document_response(session, row, DocumentDetail)

        user = session.get(JobUserRecord, row.job_id)
        if user is None:
            raise JobNotFoundError("Job application not found")
        running = session.find(JobDocument, equal={"job_id": row.job_id, "status": "running"})
        if running or (user.active_document_id is not None and user.active_document_id != row.id):
            raise EditConflictError("Another tailoring attempt is running for this job.")
        request = (
            TailorRequest.model_validate(row.request_snapshot)
            if row.request_snapshot
            else (
                TailorRequest(
                    request_id=row.id,
                    include_resume=any(
                        s.get("key") == "resume" and s.get("message") != "Not selected"
                        for s in row.stages
                    ),
                    include_cover_letter=any(
                        s.get("key") == "cover_letter" and s.get("message") != "Not selected"
                        for s in row.stages
                    ),
                )
            )
        )
        settings = AiModelOptions.model_validate(row.ai_options or {}).apply(settings)
        request.research_ai_options = AiModelOptions.model_validate(row.research_ai_options or {})
        request.resume_ai_options = AiModelOptions.model_validate(row.resume_ai_options or {})
        request.cover_letter_ai_options = AiModelOptions.model_validate(
            row.cover_letter_ai_options or {}
        )
        request.reviewer_ai_options = AiModelOptions.model_validate(row.reviewer_ai_options or {})
        for key, label, model in (
            ("pdf_diagnostics", "PDF diagnostics", "Local checks"),
            ("reviewer", "Independent reviewer", request.reviewer_ai_options.apply(settings).model),
        ):
            if not any(stage.get("key") == key for stage in row.stages):
                row.stages.append(
                    {
                        "key": key,
                        "label": label,
                        "model": model,
                        "status": "queued",
                        "message": "Waiting for documents",
                    }
                )
        target = (
            TailoringJob.model_validate(row.target_snapshot)
            if row.target_snapshot
            else (
                TailoringJob(
                    company=row.company, title=row.title, raw_description=row.job_description
                )
            )
        )
        if review.action == "generate_generic":
            request.research_mode = "generic"
            request.research_prompt = (
                review.research_prompt or ""
            ).strip() or generic_research_prompt(target.company, target.title)
            row.request_snapshot = json_object.validate_python(request.model_dump(mode="json"))
            for stage in row.stages:
                if stage.get("key") == "research":
                    stage.update(
                        status="queued", message="Preparing generic company and role research"
                    )
                elif stage.get("message") != "Not selected":
                    stage.update(status="queued", message="Waiting for generic research")
        profile = UserProfile.model_validate(row.profile_snapshot)
        user.active_document_id = row.id
        row.status = "running"
        row.started_at = now
        session.flush()
        return PreparedTailoring(
            request,
            settings,
            target,
            profile,
            row.profile_revision,
            document_response(session, row, DocumentDetail),
            regenerate_research=review.action == "generate_generic",
        )
