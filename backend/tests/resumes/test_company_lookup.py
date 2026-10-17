import json
from collections.abc import Callable

import httpx2
from pydantic import JsonValue, TypeAdapter

from job_backend.resumes.research.analyze import analyze_target
from tests.resumes.helpers import completion, job, settings

KNOWLEDGE = ["Target Employer runs a marketplace for independent shops."]


def handler(urls: list[str], requests: list[str]) -> Callable[[httpx2.Request], httpx2.Response]:
    def respond(request: httpx2.Request) -> httpx2.Response:
        requests.append(request.content.decode())
        if b"company_role_source_plan" in request.content:
            return completion(json.dumps({"urls": urls}))
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
        payload = TypeAdapter(dict[str, JsonValue]).validate_json(messages[1]["content"])
        sources = TypeAdapter(list[dict[str, JsonValue]]).validate_python(payload["sources"])
        quote = str(sources[0]["text"])
        return completion(
            json.dumps(
                {
                    "mission": None,
                    "company_context": [],
                    "company_knowledge": KNOWLEDGE,
                    "role_priorities": [
                        {"finding": "Build the systems", "source_index": 0, "quote": quote}
                    ],
                    "requirements": [],
                    "tailoring_guidance": [],
                    "unknowns": [],
                }
            )
        )

    return respond


def test_failed_lookup_still_researches() -> None:
    def respond(request: httpx2.Request) -> httpx2.Response:
        if b"company_role_source_plan" in request.content:
            return completion("not json")
        return handler([], [])(request)

    report = analyze_target(job(), settings(), transport=httpx2.MockTransport(respond))
    assert report.validated and len(report.sources) == 1
    assert any("Could not look up the company website" in warning for warning in report.warnings)
