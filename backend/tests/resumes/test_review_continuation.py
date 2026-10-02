import json
from pathlib import Path
from uuid import uuid4

import httpx2
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from job_backend.jobs.models import DocumentDetail
from job_backend.main import create_app
from job_backend.resumes.dependencies import resume_ai_settings
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


def test_skip_remaining_findings(tmp_path: Path) -> None:
    calls: list[str] = []
    initial_findings: list[dict[str, JsonValue]] = [
        {
            "document": "resume",
            "category": "requirements",
            "severity": "warning",
            "draft_quote": "",
            "issue": "The graduation date does not meet this opening's eligibility window.",
            "recommendation": "Keep the actual date and assess eligibility.",
        },
        {
            "document": "cover_letter",
            "category": "writing",
            "severity": "warning",
            "draft_quote": "",
            "issue": "The API contribution needs a clearer explanation.",
            "recommendation": "Describe the supported API work.",
        },
    ]
    later_findings: list[dict[str, JsonValue]] = [
        {
            **initial_findings[0],
            "issue": "The expected graduation remains earlier than the requested date.",
            "previous_finding": {"round": 1, "finding_index": 0},
        },
        {
            "document": "cover_letter",
            "category": "writing",
            "severity": "warning",
            "draft_quote": "",
            "issue": "The new motivation does not name the company's goal.",
            "recommendation": "Tie the reason to the company's mission.",
        },
        {
            "document": "resume",
            "category": "writing",
            "severity": "suggestion",
            "draft_quote": "",
            "issue": "A shorter phrase might read better.",
            "recommendation": "Consider shortening the phrase.",
        },
    ]

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        model = str(body["model"])
        calls.append(model)
        research = research_response(request)
        if research is not None:
            return research
        if model == "review-model":
            findings = initial_findings if calls.count(model) == 1 else later_findings
            return completion(
                json.dumps({"summary": "Inspect these findings.", "findings": findings})
            )
        if model == "resume-model":
            return completion(selection().model_dump_json())
        assert model == "letter-model"
        return completion(letter_content().model_dump_json())

    app = create_app(tmp_path / "skip-review", resume_transport=httpx2.MockTransport(handler))
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/resumes/profile", json=resume().model_dump())
        target = client.post("/jobs", json=job().model_dump(exclude={"qualifications"})).json()
        identifier = str(uuid4())
        response = client.post(
            f"/jobs/{target['id']}/tailor",
            json={
                "request_id": identifier,
                "research_ai_options": {"model": "research-model"},
                "resume_ai_options": {"model": "resume-model"},
                "cover_letter_ai_options": {"model": "letter-model"},
                "reviewer_ai_options": {"model": "review-model"},
            },
        )
        assert response.status_code == 200, response.text
        route = f"/documents/{identifier}/application-review"
        revised = client.post(
            route,
            json={
                "round": 1,
                "decisions": [
                    {"finding_index": 0, "action": "keep"},
                    {"finding_index": 1, "action": "revise", "guidance": "Use my API work."},
                ],
            },
        )
        assert revised.status_code == 202, revised.text
        pending = DocumentDetail.model_validate_json(client.get(f"/documents/{identifier}").content)
        snapshot = technical(client, identifier).profile_snapshot
        assert snapshot is not None
        assert pending.status == "awaiting_review", pending.error
        assert pending.review is not None
        assert pending.review.passes[-1].acknowledged_finding_indices == [0]
        assert len(pending.review.passes[-1].analysis.findings) == 3
        calls_before_skip = list(calls)

        for round_number, indices, expected_status in (
            (1, [1], 409),
            (2, [0, 1], 422),
            (2, [0], 422),
            (2, [1, 2], 422),
            (2, [1, 1], 422),
        ):
            rejected = client.post(
                route,
                json={
                    "round": round_number,
                    "decisions": [{"finding_index": index, "action": "keep"} for index in indices],
                },
            )
            assert rejected.status_code == expected_status, rejected.text
        assert calls == calls_before_skip

        skip = {"round": 2, "decisions": [{"finding_index": 1, "action": "keep"}]}
        accepted = client.post(route, json=skip)
        assert accepted.status_code == 202, accepted.text
        saved = DocumentDetail.model_validate_json(client.get(f"/documents/{identifier}").content)
        assert saved.status == "completed", saved.error
        assert saved.review is not None and saved.review.status == "needs_attention"
        assert saved.resume == pending.resume
        assert saved.cover_letter == pending.cover_letter
        assert saved.review.passes == pending.review.passes
        assert technical(client, identifier).profile_snapshot == snapshot
        assert len(saved.review.decisions) == 2
        assert saved.review.decisions[0] == pending.review.decisions[0]
        assert calls == calls_before_skip
        assert client.post(route, json=skip).status_code == 409
        assert calls == calls_before_skip
        assert client.get(f"/jobs/{target['id']}").json()["user"]["applied_at"] is None
