import json

import httpx2
from pydantic import JsonValue, TypeAdapter

from job_backend.resumes.models import ResearchAnalysis
from job_backend.resumes.research.generic import analyze_generic_target
from tests.resumes.helpers import (
    completion,
    job,
    settings,
)


def generic_analysis() -> ResearchAnalysis:
    return ResearchAnalysis(
        mission=None,
        company_context=[],
        role_priorities=[],
        requirements=[],
        general_role_guidance=[
            "Typical software interns implement features, debug and write tests."
        ],
        tailoring_guidance=["Highlight supported programming and testing projects."],
        unknowns=["Specific team, stack and eligibility are unknown."],
    )


def request_payload(request: httpx2.Request) -> tuple[str, dict[str, JsonValue]]:
    body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
    response_format = TypeAdapter(dict[str, JsonValue]).validate_python(body["response_format"])
    schema = TypeAdapter(dict[str, JsonValue]).validate_python(response_format["json_schema"])
    messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
    return str(schema["name"]), TypeAdapter(dict[str, JsonValue]).validate_json(
        messages[1]["content"]
    )


def test_fake_citations_rejected() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        schema, _ = request_payload(request)
        if schema == "company_role_source_plan":
            return completion('{"urls":[]}')
        analysis = generic_analysis().model_dump(mode="json")
        analysis["mission"] = {"finding": "Invented mission", "source_index": 0, "quote": "Fake"}
        return completion(json.dumps(analysis))

    report = analyze_generic_target(job(), settings(), transport=httpx2.MockTransport(handler))
    assert report.analysis.mission is None
    assert any("Invented mission" in warning for warning in report.warnings)
    assert report.validated and report.analysis.general_role_guidance
