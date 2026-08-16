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
from job_backend.resumes.models import (
    ApplicationReview,
    GeneratedCoverLetter,
    GeneratedResume,
    ReviewDecision,
    TailoringEvent,
)
from job_backend.resumes.review.review import document_hash


def decide_review(
    engine: Database, document_id: str, decision: ReviewDecision, settings: AiSettings
) -> PreparedTailoring:
    json_object = TypeAdapter(dict[str, JsonValue])
    now = int(time.time())
    with Session(engine) as session, session.begin():
        row = session.get(JobDocument, document_id)
        if row is None:
            raise JobNotFoundError("Document not found")
        review = ApplicationReview.model_validate(row.review) if row.review else None
        if (
            review is None
            or not review.passes
            or row.status not in {"awaiting_review", "failed", "completed"}
            or review.status not in {"awaiting_decision", "failed", "needs_attention"}
            or (review.status == "needs_attention" and review.decisions)
        ):
            raise EditConflictError("This attempt is not waiting for an application decision.")
        latest = review.passes[-1]
        if decision.round != latest.round:
            raise EditConflictError(
                "The review changed. Reload the latest findings before continuing."
            )
        acknowledged = set(latest.acknowledged_finding_indices)
        expected = [
            index
            for index, finding in enumerate(latest.analysis.findings)
            if finding.severity != "suggestion" and index not in acknowledged
        ]
        if sorted(item.finding_index for item in decision.decisions) != expected:
            raise ValueError(
                "Choose Keep as is or Fix for every new material finding exactly once."
            )
        documents = {
            "resume": GeneratedResume.model_validate(row.resume) if row.resume else None,
            "cover_letter": GeneratedCoverLetter.model_validate(row.cover_letter)
            if row.cover_letter
            else None,
        }
        hashes = {
            key: document_hash(value) for key, value in documents.items() if value is not None
        }
        if hashes != latest.document_hashes:
            raise EditConflictError(
                "The saved findings describe an earlier draft. Start a new tailoring attempt "
                "to review the current documents."
            )
        if row.research is None or row.profile_snapshot is None:
            raise EditConflictError("This older attempt lacks saved inputs. Start a new attempt.")
        user = session.get(JobUserRecord, row.job_id)
        if user is None:
            raise JobNotFoundError("Job application not found")
        running = session.find(JobDocument, equal={"job_id": row.job_id, "status": "running"})
        if running or user.active_document_id is not None:
            raise EditConflictError("Another tailoring attempt is running for this job.")
        request = (
            TailorRequest.model_validate(row.request_snapshot)
            if row.request_snapshot
            else TailorRequest(
                request_id=row.id,
                include_resume=row.has_resume,
                include_cover_letter=row.has_cover_letter,
            )
        )
        settings = AiModelOptions.model_validate(row.ai_options or {}).apply(settings)
        request.research_ai_options = AiModelOptions.model_validate(row.research_ai_options or {})
        request.resume_ai_options = AiModelOptions.model_validate(row.resume_ai_options or {})
        request.cover_letter_ai_options = AiModelOptions.model_validate(
            row.cover_letter_ai_options or {}
        )
        request.reviewer_ai_options = AiModelOptions.model_validate(row.reviewer_ai_options or {})
        target = (
            TailoringJob.model_validate(row.target_snapshot)
            if row.target_snapshot
            else TailoringJob(
                company=row.company, title=row.title, raw_description=row.job_description
            )
        )
        revise = any(item.action == "revise" for item in decision.decisions)
        review.decisions.append(decision)
        review.status = "revising" if revise else "needs_attention"
        row.review = json_object.validate_python(review.model_dump(mode="json"))
        row.status = "running"
        row.error = None
        row.started_at = now
        row.finished_at = None
        user.active_document_id = row.id
        message = (
            "Your choices were saved, revising the selected findings"
            if revise
            else "You chose to keep the current documents with findings acknowledged"
        )
        for stage in row.stages:
            if stage.get("key") == "reviewer":
                stage.update(status="running", message=message)
        row.events.append(
            json_object.validate_python(
                TailoringEvent(
                    id=len(row.events) + 1, created_at=now, stage="validate", message=message
                ).model_dump(mode="json")
            )
        )
        session.flush()
        return PreparedTailoring(
            request,
            settings,
            target,
            UserProfile.model_validate(row.profile_snapshot),
            row.profile_revision,
            document_response(session, row, DocumentDetail),
            resume_review=True,
        )
