import json
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.models import DocumentDetail, JobResponse, PreparedTailoring, TailorRequest
from job_backend.jobs.tailoring import prepare_tailoring
from job_backend.main import create_app
from job_backend.persistence.database import make_engine
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.generate_cover_letter.models import LetterContent
from tests.resumes.helpers import candidate_profile, completion, job, selection, settings, technical
from tests.resumes.test_cover_letter import letter_content


def _answer(request: httpx2.Request, *, omit_resume: bool = False) -> httpx2.Response:
    body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
    response_format = TypeAdapter(dict[str, JsonValue]).validate_python(body["response_format"])
    schema = TypeAdapter(dict[str, JsonValue]).validate_python(response_format["json_schema"])
    assert schema["name"] == "one_shot_application"
    messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
    for section in ("# Research rules", "# Resume rules", "# Cover letter rules"):
        assert section in messages[0]["content"]
    assert "# Review rules" in messages[0]["content"]
    assert "# Revision rules" in messages[0]["content"]
    payload = TypeAdapter(dict[str, JsonValue]).validate_json(messages[1]["content"])
    assert payload["documents_to_write"] == ["resume", "cover_letter"]
    sources = TypeAdapter(list[dict[str, JsonValue]]).validate_python(payload["sources"])
    draft_letter = LetterContent(
        paragraphs=["I am applying for this role.", *letter_content().paragraphs[1:]]
    )
    content = {
        "research": {
            "mission": None,
            "company_context": [],
            "role_priorities": [
                {
                    "finding": "Build the systems described in this role",
                    "source_index": 0,
                    "quote": str(sources[0]["text"]),
                }
            ],
            "requirements": [],
            "tailoring_guidance": ["Use supported relevant experience"],
            "unknowns": ["Company mission is not stated"],
        },
        "resume_draft": selection().model_dump(mode="json"),
        "cover_letter_draft": draft_letter.model_dump(mode="json"),
        "review": {
            "summary": "The letter opens with an application announcement.",
            "findings": [
                {
                    "document": "cover_letter",
                    "category": "writing",
                    "severity": "warning",
                    "draft_quote": "I am applying for this role.",
                    "issue": "Generic opening",
                    "recommendation": "Lead with the company's work.",
                }
            ],
        },
        "resume": None if omit_resume else selection().model_dump(mode="json"),
        "cover_letter": letter_content().model_dump(mode="json"),
    }
    return completion(json.dumps(content))


@pytest.mark.parametrize("omit_resume", [False, True])
def test_one_shot_single_call(tmp_path: Path, omit_resume: bool) -> None:
    calls: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        calls.append(str(body["model"]))
        return _answer(request, omit_resume=omit_resume)

    app = create_app(tmp_path / "one-shot", resume_transport=httpx2.MockTransport(handler))
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/profile", json={"profile": candidate_profile().model_dump(), "revision": 0})
        target = JobResponse.model_validate_json(
            client.post("/jobs", json=job().model_dump(exclude={"qualifications"})).content
        )
        request_id = str(uuid4())
        result = client.post(
            f"/jobs/{target.id}/tailor",
            json={
                "request_id": request_id,
                "mode": "one_shot",
                "one_shot_ai_options": {"model": "one-shot-model"},
            },
        )
        saved = DocumentDetail.model_validate_json(client.get(f"/documents/{request_id}").content)
        assert calls == ["one-shot-model"]
        if omit_resume:
            assert result.status_code == 502, result.text
            assert saved.status == "failed"
            assert "did not include the final resume" in (saved.error or "")
            return
        assert result.status_code == 200, result.text
        assert saved.status == "completed"
        assert saved.mode == "one_shot" and saved.one_shot_step == "revise"
        assert any(
            event.message == "Research: One call revising into the final documents"
            for event in saved.events
        )
        assert saved.resume is not None and saved.cover_letter is not None
        assert saved.cover_letter.paragraphs == letter_content().paragraphs
        assert saved.research is not None and saved.research.validated
        assert saved.review is not None and saved.review.status == "completed"
        assert [len(item.analysis.findings) for item in saved.review.passes] == [1]
        assert saved.review.revised_documents == ["cover_letter"]
        assert {stage.key: stage.status for stage in saved.stages} == {
            "research": "completed",
            "resume": "completed",
            "cover_letter": "completed",
            "pdf_diagnostics": "completed",
            "reviewer": "completed",
        }
        assert {stage.model for stage in saved.stages} == {"one-shot-model", "Local checks"}
        logs = technical(client, saved.id)
        steps = [(item.stage, item.content.get("step")) for item in logs.reports]
        assert ("resume", "One-shot first draft") in steps
        assert ("cover_letter", "One-shot first draft") in steps
        assert ("reviewer", "One-shot self-review") in steps


def test_one_shot_default_model(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "defaults")
    app = create_app(tmp_path / "defaults", resume_transport=httpx2.MockTransport(_answer))
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/profile", json={"profile": candidate_profile().model_dump(), "revision": 0})
        target = JobResponse.model_validate_json(
            client.post("/jobs", json=job().model_dump(exclude={"qualifications"})).content
        )
        prepared = prepare_tailoring(
            engine,
            target.id,
            TailorRequest(request_id=str(uuid4()), mode="one_shot"),
            settings(),
        )
        assert isinstance(prepared, PreparedTailoring)
        options = prepared.request.one_shot_ai_options
        assert options is not None
        assert (options.provider, options.model, options.reasoning_effort) == (None, None, None)
        assert prepared.settings.provider == "endpoint"
        assert prepared.settings.model == settings().model
        assert {stage.model for stage in prepared.document.stages} == {
            settings().model,
            "Local checks",
        }
