import json
import time
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.models import DocumentDetail, JobDocument, JobUserRecord
from job_backend.main import create_app
from job_backend.persistence.database import make_engine
from job_backend.persistence.session import Session
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.models import ReviewDecision
from tests.resumes.helpers import (
    completion,
    job,
    research_response,
    resume,
    selection,
    settings,
    technical,
)
from tests.resumes.test_cover_letter import letter_content


@pytest.mark.parametrize("action", ["keep", "mixed", "revise"])
def test_resume_selected_writers(tmp_path: Path, action: str) -> None:
    calls: list[str] = []
    findings = [
        {
            "document": "resume",
            "category": "requirements",
            "severity": "warning",
            "draft_quote": "",
            "issue": "Graduation date does not meet the requirement.",
            "recommendation": "Keep the actual date and assess eligibility.",
        },
        {
            "document": "cover_letter",
            "category": "writing",
            "severity": "warning",
            "draft_quote": "",
            "issue": "Clarify the API contribution.",
            "recommendation": "Use the saved evidence for the API work.",
        },
    ]

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        model = str(body["model"])
        calls.append(model)
        research = research_response(request)
        if research is not None:
            return research
        messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
        payload = TypeAdapter(dict[str, JsonValue]).validate_json(messages[1]["content"])
        if model == "review-model":
            if calls.count(model) == 1:
                assert "review_history" not in payload
            else:
                history = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
                    payload["review_history"]
                )
                assert len(history) == calls.count(model) - 1
                assert history[0]["findings"] == findings
                choices = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
                    history[0]["decisions"]
                )
                assert len(choices) == 2
                assert choices[0]["action"] == ("keep" if action == "mixed" else "revise")
                assert all(item["guidance"] == "Use the saved API evidence." for item in choices)
            current = (
                findings if calls.count(model) == 1 else (findings[:1] if action == "mixed" else [])
            )
            return completion(
                json.dumps(
                    {"summary": "Check requirements before continuing.", "findings": current}
                )
            )
        if calls.count(model) > 1:
            revision = TypeAdapter(dict[str, JsonValue]).validate_python(payload["review_revision"])
            chosen = TypeAdapter(list[dict[str, JsonValue]]).validate_python(revision["findings"])
            assert all(item["user_guidance"] == "Use the saved API evidence." for item in chosen)
            history = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
                revision["review_history"]
            )
            assert history[0]["findings"] == findings
            assert len(history) == calls.count("review-model")
            assert all(history_round["decisions"] for history_round in history)
            assert "Honor earlier keep choices" in messages[0]["content"]
            assert "instructions" not in payload
        if model == "resume-model":
            return completion(selection().model_dump_json())
        assert model == "letter-model"
        return completion(letter_content().model_dump_json())

    path = tmp_path / "decisions"
    app = create_app(path, resume_transport=httpx2.MockTransport(handler))
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/resumes/profile", json=resume().model_dump())
        target = client.post("/jobs", json=job().model_dump(exclude={"qualifications"})).json()
        identifier = str(uuid4())
        request = {
            "request_id": identifier,
            "research_ai_options": {"model": "research-model"},
            "resume_ai_options": {"model": "resume-model"},
            "cover_letter_ai_options": {"model": "letter-model"},
            "reviewer_ai_options": {"model": "review-model"},
        }
        initial = client.post(f"/jobs/{target['id']}/tailor", json=request)
        assert initial.status_code == 200, initial.text
        paused = DocumentDetail.model_validate_json(initial.content)
        assert paused.status == "awaiting_review" and paused.review is not None
        assert paused.review.status == "awaiting_decision" and len(calls) == 5
        assert paused.resume is not None and paused.cover_letter is not None
        assert client.get(f"/documents/{identifier}").content == initial.content
        snapshot = technical(client, identifier).profile_snapshot
        assert snapshot is not None and paused.profile_snapshot is None
        assert client.get(f"/documents/{identifier}/resume/tex").status_code == 200
        engine = make_engine(path)
        with Session(engine) as session, session.begin():
            user = session.get(JobUserRecord, target["id"])
            assert user is not None and user.active_document_id is None
            row = session.get(JobDocument, identifier)
            assert row is not None
            row.created_at = int(time.time()) - 30 * 86400
            row.started_at = row.created_at
        engine.dispose()
        with TestClient(create_app(path)) as reopened:
            restored = DocumentDetail.model_validate_json(
                reopened.get(f"/documents/{identifier}").content
            )
            assert restored.status == "awaiting_review" and restored.error is None
            assert restored.review == paused.review and restored.events == paused.events
            assert restored.resume == paused.resume and restored.cover_letter == paused.cover_letter
            assert technical(reopened, identifier).profile_snapshot == snapshot
            summaries = reopened.get(f"/jobs/{target['id']}").json()["user"]["documents"]
            assert summaries[0]["id"] == identifier
            assert summaries[0]["status"] == "awaiting_review"
        assert len(calls) == 5
        (tmp_path / "review-preview.json").write_text(paused.model_dump_json(), encoding="utf-8")
        assert paused.research is not None
        assert (
            client.post(
                f"/documents/{identifier}/research-review",
                json={"revision": paused.research.revision, "action": "continue"},
            ).status_code
            == 409
        )
        decision = ReviewDecision.model_validate(
            {
                "round": 1,
                "decisions": [
                    {
                        "finding_index": index,
                        "action": "keep"
                        if action == "keep" or (action == "mixed" and index == 0)
                        else "revise",
                        "guidance": "Use the saved API evidence.",
                    }
                    for index in range(2)
                ],
            }
        )
        route = f"/documents/{identifier}/application-review"
        assert (
            client.post(route, json={**decision.model_dump(mode="json"), "round": 99}).status_code
            == 409
        )
        assert (
            client.post(
                route,
                json={
                    **decision.model_dump(mode="json"),
                    "decisions": [item.model_dump(mode="json") for item in decision.decisions[:1]],
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                route,
                json={
                    **decision.model_dump(mode="json"),
                    "decisions": [item.model_dump(mode="json") for item in decision.decisions[:1]]
                    * 2,
                },
            ).status_code
            == 422
        )
        assert len(calls) == 5
        engine = make_engine(path)
        with Session(engine) as session, session.begin():
            user = session.get(JobUserRecord, target["id"])
            assert user is not None
            user.active_document_id = "another-attempt"
        assert client.post(route, json=decision.model_dump(mode="json")).status_code == 409
        with Session(engine) as session, session.begin():
            user = session.get(JobUserRecord, target["id"])
            assert user is not None
            user.active_document_id = None
        engine.dispose()
        assert len(calls) == 5
        changed = resume()
        changed.name = "Different candidate"
        client.put("/resumes/profile", json=changed.model_dump())
        accepted = client.post(route, json=decision.model_dump(mode="json"))
        assert accepted.status_code == 202, accepted.text
        engine = make_engine(path)
        with Session(engine) as session:
            row = session.get(JobDocument, identifier)
            assert row is not None and row.started_at is not None
            assert row.started_at >= int(time.time()) - 60
        engine.dispose()
        saved = DocumentDetail.model_validate_json(client.get(f"/documents/{identifier}").content)
        assert saved.review is not None, saved.error
        assert saved.error is None, saved.error
        assert saved.review.decisions[0].round == 1
        assert calls.count("research-model") == 2
        assert calls.count("resume-model") == (1 if action in {"keep", "mixed"} else 2)
        assert calls.count("letter-model") == (1 if action == "keep" else 2)
        assert calls.count("review-model") == (1 if action == "keep" else 2)
        assert (
            technical(client, identifier).profile_snapshot == snapshot
            and saved.research == paused.research
        )
        assert saved.status == "completed"
        assert saved.review.status == (
            "needs_attention" if action in {"keep", "mixed"} else "completed"
        )
        before = list(calls)
        assert client.post(route, json=decision.model_dump(mode="json")).status_code == 409
        assert calls == before
        assert client.get(f"/jobs/{target['id']}").json()["user"]["applied_at"] is None


def test_changed_drafts_rejected(tmp_path: Path) -> None:
    from job_backend.jobs.review_decisions import decide_review
    from job_backend.jobs.user_service import EditConflictError

    engine = make_engine(tmp_path / "stale")
    review: dict[str, JsonValue] = {
        "status": "awaiting_decision",
        "revised_documents": [],
        "passes": [
            {
                "round": 1,
                "analysis": {
                    "summary": "One issue",
                    "findings": [
                        {
                            "document": "resume",
                            "category": "requirements",
                            "severity": "warning",
                            "draft_quote": "",
                            "issue": "Date mismatch",
                            "recommendation": "Keep actual dates",
                        }
                    ],
                },
                "document_hashes": {"resume": "a" * 64},
                "ai_usage": {
                    "model_name": "test",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "calls": 1,
                },
            }
        ],
    }
    with Session(engine) as session, session.begin():
        session.add(
            JobDocument(id=str(uuid4()), job_id="job", status="awaiting_review", review=review)
        )
    with Session(engine) as session:
        identifier = session.find(JobDocument)[0].id
    decision = ReviewDecision.model_validate(
        {"round": 1, "decisions": [{"finding_index": 0, "action": "keep"}]}
    )
    with pytest.raises(EditConflictError, match="earlier draft"):
        decide_review(engine, identifier, decision, settings())
    engine.dispose()
