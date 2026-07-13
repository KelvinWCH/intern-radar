import json
from pathlib import Path
from threading import Barrier, Lock
from uuid import uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.models import DocumentDetail, JobDocument, JobResponse
from job_backend.main import create_app
from job_backend.persistence.database import make_engine
from job_backend.persistence.session import Session
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.research.analyze import analyze_target
from tests.resumes.helpers import (
    candidate_profile,
    completion,
    job,
    research_response,
    reviewer_response,
    selection,
    settings,
    site_lookup_response,
    technical,
)
from tests.resumes.test_cover_letter import letter_content


@pytest.mark.parametrize("fail_letter", [False, True])
def test_parallel_writers(tmp_path: Path, fail_letter: bool) -> None:
    calls: list[str] = []
    lock = Lock()
    writers = Barrier(2, timeout=5)

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        model = str(body["model"])
        with lock:
            calls.append(model)
        if model == "reviewer-model":
            response = reviewer_response(request)
            assert response is not None
            return response
        if model == "research-model":
            response = research_response(request)
            assert response is not None
            return response
        messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
        payload = TypeAdapter(dict[str, JsonValue]).validate_json(messages[1]["content"])
        research = TypeAdapter(dict[str, JsonValue]).validate_python(
            payload["company_role_research"]
        )
        assert research["validated"] is True
        assert calls[0] == "research-model"
        assert "Complete personal story" in json.dumps(payload["user_resume"])
        writers.wait()
        if model == "resume-model":
            return completion(selection().model_dump_json())
        assert model == "letter-model"
        return completion("{}" if fail_letter else letter_content().model_dump_json())

    app = create_app(tmp_path / "workflow", resume_transport=httpx2.MockTransport(handler))
    app.dependency_overrides[resume_ai_settings] = settings
    profile = candidate_profile()
    profile.about = "Complete personal story"
    with TestClient(app) as client:
        client.put("/profile", json={"profile": profile.model_dump(), "revision": 0})
        target = JobResponse.model_validate_json(
            client.post("/jobs", json=job().model_dump(exclude={"qualifications"})).content
        )
        request = {
            "request_id": str(uuid4()),
            "research_ai_options": {"model": "research-model"},
            "resume_ai_options": {"model": "resume-model"},
            "cover_letter_ai_options": {"model": "letter-model"},
            "reviewer_ai_options": {"model": "reviewer-model"},
        }
        result = client.post(f"/jobs/{target.id}/tailor", json=request)
        assert result.status_code == (502 if fail_letter else 200), result.text
        saved = DocumentDetail.model_validate_json(
            client.get(f"/documents/{request['request_id']}").content
        )
        assert saved.research is not None and saved.research.validated
        assert saved.research.sources[0].text == job().raw_description
        logs = technical(client, saved.id)
        assert saved.reports == [] and saved.profile_snapshot is None
        assert logs.profile_snapshot == profile.model_dump(mode="json")
        assert saved.resume is not None
        assert logs.reports[0].content["input"] is not None
        assert logs.reports[0].content["system_prompt"]
        assert {stage.model for stage in saved.stages} == {
            "research-model",
            "resume-model",
            "letter-model",
            "reviewer-model",
            "Local checks",
        }
        assert {stage.key: stage.status for stage in saved.stages} == {
            "research": "completed",
            "resume": "completed",
            "cover_letter": "failed" if fail_letter else "completed",
            "reviewer": "skipped" if fail_letter else "completed",
            "pdf_diagnostics": "failed" if fail_letter else "completed",
        }
        assert client.get(f"/documents/{saved.id}/resume/tex").status_code == 200
        assert client.get(f"/jobs/{target.id}").json()["user"]["applied_at"] is None
        assert len(logs.reports) == (4 if fail_letter else 5)
        if fail_letter:
            failed_report = next(item for item in logs.reports if item.stage == "cover_letter")
            assert failed_report.content["output"] == {}
            assert "schema" in (saved.error or "")
        if not fail_letter:
            assert len(logs.reports) == 5
            assert client.post(f"/jobs/{target.id}/tailor", json=request).content == result.content
        assert sorted(calls) == [
            "letter-model",
            "research-model",
            "research-model",
            "resume-model",
        ] + ([] if fail_letter else ["reviewer-model"])


@pytest.mark.parametrize("edit", ["none", "unverified", "verified"])
def test_invalid_research_pauses(tmp_path: Path, edit: str) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        response = site_lookup_response(request) or reviewer_response(request)
        if response is not None:
            return response
        calls += 1
        if calls > 1:
            body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
            messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
            payload = TypeAdapter(dict[str, JsonValue]).validate_json(messages[1]["content"])
            research = TypeAdapter(dict[str, JsonValue]).validate_python(
                payload["company_role_research"]
            )
            assert research["approved_at"] is not None
            assert research["validated"] is (edit == "verified")
            assert "Original profile story" in json.dumps(payload["user_resume"])
            assert payload["candidate_instructions"] == "Keep it concise"
            if edit in {"unverified", "verified"}:
                assert "Edited mission" in json.dumps(research["analysis"])
            return completion(selection().model_dump_json())
        return completion(
            json.dumps(
                {
                    "mission": {
                        "finding": "Unsupported mission",
                        "source_index": 0,
                        "quote": "This quote is not in the source",
                    },
                    "company_context": [],
                    "role_priorities": [],
                    "requirements": [],
                    "tailoring_guidance": [],
                    "unknowns": [],
                }
            )
        )

    engine = make_engine(tmp_path / "invalid")
    app = create_app(tmp_path / "invalid", resume_transport=httpx2.MockTransport(handler))
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        profile = candidate_profile()
        profile.about = "Original profile story"
        client.put("/profile", json={"profile": profile.model_dump(), "revision": 0})
        target = JobResponse.model_validate_json(
            client.post("/jobs", json=job().model_dump(exclude={"qualifications"})).content
        )
        request_id = str(uuid4())
        assert (
            client.post(
                f"/jobs/{target.id}/tailor",
                json={
                    "request_id": request_id,
                    "include_cover_letter": False,
                    "instructions": "Keep it concise",
                },
            ).status_code
            == 200
        )
        saved = DocumentDetail.model_validate_json(client.get(f"/documents/{request_id}").content)
        assert saved.research is not None and not saved.research.validated
        assert saved.status == "awaiting_review" and saved.error is None
        assert saved.finished_at is None and saved.research.validation_issues
        assert saved.stages[0].status == "awaiting_review"
        assert saved.stages[1].status == "queued" and saved.stages[2].status == "skipped"
        logs = technical(client, saved.id)
        assert calls == 1 and [report.stage for report in logs.reports] == ["research", "research"]
        assert (
            client.post(
                f"/documents/{request_id}/research-review",
                json={"revision": 1, "action": "continue", "validated": True, "sources": []},
            ).status_code
            == 422
        )
        assert client.get(f"/documents/{request_id}/resume/tex").status_code == 409
        review_url = f"/documents/{request_id}/research-review"
        assert (
            client.post(review_url, json={"revision": 99, "action": "continue"}).status_code == 409
        )
        if edit in {"unverified", "verified"}:
            analysis = saved.research.analysis.model_dump(mode="json")
            analysis["mission"] = {
                "finding": "Edited mission",
                "source_index": 0,
                "quote": job().raw_description if edit == "verified" else "",
            }
            analysis["role_priorities"] = [
                {
                    "finding": "Work on the described systems",
                    "source_index": 0,
                    "quote": job().raw_description,
                }
            ]
            response = client.post(
                review_url, json={"revision": 1, "action": "save", "analysis": analysis}
            )
            assert response.status_code == 202, response.text
            saved = DocumentDetail.model_validate_json(response.content)
            assert saved.status == "awaiting_review" and calls == 1
            assert saved.research is not None
            assert saved.research.validated is (edit == "verified")
            assert saved.research.approved_at is None
            assert (
                client.post(review_url, json={"revision": 1, "action": "continue"}).status_code
                == 409
            )
        profile.about = "Changed after research"
        client.put("/profile", json={"profile": profile.model_dump(), "revision": 1})
        with Session(engine) as session, session.begin():
            row = session.get(JobDocument, request_id)
            assert row is not None
            row.created_at = 1
            row.started_at = 1
        with TestClient(create_app(tmp_path / "invalid")) as reopened:
            restored = DocumentDetail.model_validate_json(
                reopened.get(f"/documents/{request_id}").content
            )
            assert restored.status == "awaiting_review" and restored.error is None
            assert restored.research == saved.research and restored.events == saved.events
            assert technical(reopened, request_id).profile_snapshot == logs.profile_snapshot
        review = {"revision": saved.research.revision, "action": "continue"}
        response = client.post(review_url, json=review)
        assert response.status_code == 202, response.text
        finished = DocumentDetail.model_validate_json(
            client.get(f"/documents/{request_id}").content
        )
        assert finished.status == "completed", finished.error
        assert finished.research is not None and finished.research.approved_at is not None
        assert finished.research.validated is (edit == "verified")
        assert finished.ai_usage is not None and finished.ai_usage.calls == 4
        assert len(technical(client, request_id).reports) == 4 and calls == 2
        assert client.post(review_url, json=review).status_code == 409
        assert calls == 2
        assert client.get(f"/jobs/{target.id}").json()["user"]["applied_at"] is None


@pytest.mark.parametrize("missing", ["quote", "source", "findings"])
def test_unverifiable_research(missing: str) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return completion(
            json.dumps(
                {
                    "mission": None
                    if missing == "findings"
                    else {
                        "finding": "A claim",
                        "quote": "" if missing == "quote" else "A quote",
                        "source_index": 10 if missing == "source" else 0,
                    },
                    "company_context": [],
                    "role_priorities": [],
                    "requirements": [],
                    "tailoring_guidance": [],
                    "unknowns": [],
                }
            )
        )

    report = analyze_target(job(), settings(), transport=httpx2.MockTransport(handler))
    assert not report.validated and report.validation_issues and report.approved_at is None


def test_private_url_rejected() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        response = research_response(request)
        assert response is not None
        return response

    report = analyze_target(
        job(), settings(), company_url="http://127.0.0.1/", transport=httpx2.MockTransport(handler)
    )
    assert len(report.sources) == 1 and report.warnings and report.validated
