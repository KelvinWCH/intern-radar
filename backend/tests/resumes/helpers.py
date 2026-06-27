import json

import httpx2
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from job_backend.common.models import AiSettings
from job_backend.jobs.models import DocumentTechnicalDetails, TailoringJob
from job_backend.profile.models import UserProfile
from job_backend.resumes.generate_resume.models import (
    EntrySelection,
    SupportedBullet,
    TailoredContent,
)
from job_backend.resumes.models import (
    Experience,
    Project,
    SourceEducation,
    SourceSection,
    SourceSkillGroup,
    UserResume,
)


def technical(client: TestClient, document_id: str) -> DocumentTechnicalDetails:
    response = client.get(f"/documents/{document_id}/technical")
    assert response.status_code == 200, response.text
    return DocumentTechnicalDetails.model_validate_json(response.content)


def settings() -> AiSettings:
    return AiSettings(base_url="http://localhost:1234/v1", model="fictional")


def resume() -> UserResume:
    return UserResume(
        name="Alex Example",
        email="alex_example@example.com",
        phone=None,
        location="Toronto, ON",
        links=["https://example.com/alex"],
        skills=[
            SourceSkillGroup(category="Languages & tools", items=["Python", "Redis", "TypeScript"])
        ],
        education=[
            SourceEducation(
                institution="Example University",
                degree="BSc",
                field_of_study="Computer Science",
                location="Toronto",
                start_date="2024",
                end_date="Expected 2028",
                bullets=["GPA: 3.8/4.0"],
            )
        ],
        experience=[
            Experience(
                company="Example & Co",
                title="Software Intern",
                location="Toronto",
                start_date="May 2026",
                end_date="August 2026",
                bullets=["Built Python APIs."],
                raw_description="Built Python APIs. Added Redis caching that reduced p95 latency "
                "by 25% in a staging benchmark. Internal notes: keep this context unprinted.",
            )
        ],
        projects=[
            Project(
                name="Search_Project",
                url=None,
                technologies=["Python"],
                start_date=None,
                end_date=None,
                bullets=["Built a search service."],
                raw_description="Built a search service. Created a benchmark of 500 queries; "
                "improved median response time by 30% on that benchmark.",
            )
        ],
        additional_sections=[SourceSection(title="Awards", items=["Department scholarship"])],
    )


def job() -> TailoringJob:
    return TailoringJob(
        company="Target Employer",
        title="Backend Intern",
        raw_description="Build Python APIs, use Redis, and benchmark search performance.",
    )


def selection() -> TailoredContent:
    return TailoredContent(
        experience=[
            EntrySelection(
                source_index=0,
                bullets=[
                    SupportedBullet(
                        source_bullet=None,
                        text="Added Redis caching to Python APIs, reducing p95 latency "
                        "by 25% in staging.",
                    ),
                    SupportedBullet(
                        source_bullet=0,
                        text="Built Python APIs.",
                    ),
                ],
            )
        ],
        projects=[
            EntrySelection(
                source_index=0,
                bullets=[
                    SupportedBullet(
                        source_bullet=0,
                        text="Built a search service.",
                    ),
                    SupportedBullet(
                        source_bullet=None,
                        text="Benchmarked 500 search queries and improved median response time "
                        "by 30% on that benchmark.",
                    ),
                ],
            )
        ],
        skill_selections=[],
    )


def completion(content: str) -> httpx2.Response:
    return httpx2.Response(
        200,
        json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
    )


def candidate_profile(source: UserResume | None = None) -> UserProfile:
    return UserProfile.model_validate((source or resume()).model_dump())


def site_lookup_response(request: httpx2.Request) -> httpx2.Response | None:
    if b"company_role_source_plan" not in request.content:
        return None
    return httpx2.Response(
        200,
        json={
            "choices": [{"message": {"content": '{"urls": []}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        },
    )


def research_response(request: httpx2.Request) -> httpx2.Response | None:
    body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
    response_format = TypeAdapter(dict[str, JsonValue]).validate_python(body["response_format"])
    schema = TypeAdapter(dict[str, JsonValue]).validate_python(response_format["json_schema"])
    if schema["name"] == "company_role_source_plan":
        return site_lookup_response(request)
    if schema["name"] != "company_role_research":
        return None
    messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
    payload = TypeAdapter(dict[str, JsonValue]).validate_json(messages[1]["content"])
    sources = TypeAdapter(list[dict[str, JsonValue]]).validate_python(payload["sources"])
    quote = str(sources[0]["text"])
    content = json.dumps(
        {
            "mission": None,
            "company_context": [],
            "role_priorities": [
                {
                    "finding": "Build the systems described in this role",
                    "source_index": 0,
                    "quote": quote,
                }
            ],
            "requirements": [],
            "tailoring_guidance": ["Use supported relevant experience"],
            "unknowns": ["Company mission is not stated"],
        }
    )
    return httpx2.Response(
        200,
        json={
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        },
    )


def reviewer_response(request: httpx2.Request) -> httpx2.Response | None:
    body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
    response_format = TypeAdapter(dict[str, JsonValue]).validate_python(body["response_format"])
    schema = TypeAdapter(dict[str, JsonValue]).validate_python(response_format["json_schema"])
    if schema["name"] != "application_review":
        return None
    return httpx2.Response(
        200,
        json={
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "summary": "No material findings in the supplied drafts.",
                                "findings": [],
                            }
                        )
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        },
    )


def workflow_response(request: httpx2.Request) -> httpx2.Response | None:
    return reviewer_response(request) or research_response(request)


def completion_event(content: str = "", *, finish: str | None = None, index: int = 0) -> bytes:
    return (
        "data: "
        + json.dumps(
            {"choices": [{"index": index, "delta": {"content": content}, "finish_reason": finish}]},
            ensure_ascii=False,
        )
        + "\r\n\r\n"
    ).encode()
