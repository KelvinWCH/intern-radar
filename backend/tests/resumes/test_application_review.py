import json
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.models import DocumentDetail, JobResponse
from job_backend.main import create_app
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.review.review import document_hash
from tests.resumes.helpers import (
    completion,
    job,
    research_response,
    resume,
    selection,
    settings,
)
from tests.resumes.test_cover_letter import letter_content


@pytest.mark.parametrize("persistent", [False, True])
def test_review_revises_once(tmp_path: Path, persistent: bool) -> None:
    calls: list[str] = []
    review_calls = 0
    writer_calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal review_calls, writer_calls
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        model = str(body["model"])
        calls.append(model)
        response = research_response(request)
        if response is not None:
            return response
        messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
        payload = TypeAdapter(dict[str, JsonValue]).validate_json(messages[1]["content"])
        if model == "reviewer-model":
            review_calls += 1
            assert "documents" in payload and "user_resume" in payload
            if review_calls == 1:
                assert "review_history" not in payload
            else:
                history = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
                    payload["review_history"]
                )
                assert len(history) == 1
                assert history[0]["decisions"] == []
                assert "findings" in history[0]
            findings: list[dict[str, str]] = []
            if review_calls == 1 or persistent:
                findings = [
                    {
                        "document": "resume",
                        "category": "writing",
                        "severity": "warning",
                        "draft_quote": "",
                        "issue": "Clarify the contribution to the API work.",
                        "recommendation": "Use the supported work from the same entry.",
                    }
                ]
            return completion(
                json.dumps({"summary": "Review of supplied drafts", "findings": findings})
            )
        if model == "resume-model":
            writer_calls += 1
            if writer_calls == 2:
                assert "review_revision" in payload
                revision = TypeAdapter(dict[str, JsonValue]).validate_python(
                    payload["review_revision"]
                )
                assert "review_history" in revision
                assert "untrusted advice" in messages[0]["content"]
            draft = selection()
            if writer_calls == 2:
                draft.experience[0].bullets[0].text = "Built Python APIs."
            return completion(draft.model_dump_json())
        assert model == "letter-model"
        assert "review_revision" not in payload
        return completion(letter_content().model_dump_json())

    app = create_app(tmp_path / "review", resume_transport=httpx2.MockTransport(handler))
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/resumes/profile", json=resume().model_dump())
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
        response = client.post(f"/jobs/{target.id}/tailor", json=request)
        assert response.status_code == 200, response.text
        result = DocumentDetail.model_validate_json(response.content)
        assert (
            result.review is not None
            and result.resume is not None
            and result.cover_letter is not None
        )
        assert result.review.status == ("awaiting_decision" if persistent else "completed")
        assert result.review.revised_documents == ["resume"]
        assert len(result.review.passes) == 2 and writer_calls == review_calls == 2
        assert result.review.passes[-1].document_hashes["resume"] == document_hash(result.resume)
        assert result.review.passes[0].document_hashes["resume"] != document_hash(result.resume)
        assert len(result.pdf_diagnostics) == 2
        assert {report.document: report.document_sha256 for report in result.pdf_diagnostics} == {
            "resume": document_hash(result.resume),
            "cover_letter": document_hash(result.cover_letter),
        }
        assert all(
            report.extracted_text == "Fictional sample document"
            for report in result.pdf_diagnostics
        )
        assert all(
            stage.status
            == ("awaiting_review" if persistent and stage.key == "reviewer" else "completed")
            for stage in result.stages
        )
        assert result.status == ("awaiting_review" if persistent else "completed")
        assert result.ai_usage is not None and result.ai_usage.calls == 7
        assert (
            result.reviewer_ai_options is not None
            and result.reviewer_ai_options.model == "reviewer-model"
        )
        assert client.get(f"/jobs/{target.id}").json()["user"]["applied_at"] is None
        if not persistent:
            assert (
                client.post(f"/jobs/{target.id}/tailor", json=request).content == response.content
            )
        else:
            assert client.get(f"/documents/{result.id}").content == response.content
        assert len(calls) == 7


@pytest.mark.parametrize("finding", ["invented_quote", "absent_document"])
def test_ungrounded_findings_dropped(tmp_path: Path, finding: str) -> None:
    writer_calls = 0
    grounded = {
        "document": "resume",
        "category": "writing",
        "severity": "suggestion",
        "draft_quote": "built  python apis",
        "issue": "Name the API's users.",
        "recommendation": "Use the supported scale.",
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal writer_calls
        response = research_response(request)
        if response is not None:
            return response
        if b"application_review" in request.content:
            invented = {
                **grounded,
                "document": "cover_letter" if finding == "absent_document" else "resume",
                "severity": "error",
                "draft_quote": "Invented quotation" if finding == "invented_quote" else "",
                "issue": "Review this claim",
            }
            return completion(
                json.dumps({"summary": "Two issues", "findings": [invented, grounded]})
            )
        writer_calls += 1
        return completion(selection().model_dump_json())

    app = create_app(tmp_path / "dropped", resume_transport=httpx2.MockTransport(handler))
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/resumes/profile", json=resume().model_dump())
        target = JobResponse.model_validate_json(
            client.post("/jobs", json={"raw_description": "Required skills: Python"}).content
        )
        request = {"request_id": str(uuid4()), "include_cover_letter": False}
        response = client.post(f"/jobs/{target.id}/tailor", json=request)
        assert response.status_code == 200, response.text
        saved = DocumentDetail.model_validate_json(response.content)
    assert saved.status == "completed" and saved.review is not None
    assert [item.issue for item in saved.review.passes[0].analysis.findings] == [grounded["issue"]]
    assert writer_calls == 1 and saved.review.status == "completed"
