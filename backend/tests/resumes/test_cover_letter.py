import httpx2
import pytest
from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.common.ai_completion import AiCompletionError
from job_backend.resumes.generate_cover_letter.generate import generate_cover_letter
from job_backend.resumes.generate_cover_letter.models import LetterContent
from job_backend.resumes.models import GeneratedCoverLetter, UserResume
from tests.resumes.helpers import completion, job, resume, settings


def letter_content() -> LetterContent:
    return LetterContent(
        paragraphs=[
            "Building Python APIs connects my experience to Target Employer's backend work.",
            "I added Redis caching that reduced p95 latency by 25% in staging.",
            "Thank you for considering my application.",
        ]
    )


def test_cover_letter_uses_profile() -> None:
    source = resume()
    before = source.model_dump_json()

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
        payload = TypeAdapter(dict[str, JsonValue]).validate_json(messages[1]["content"])
        assert UserResume.model_validate(payload["user_resume"]) == source
        assert "Internal notes" in messages[1]["content"]
        return completion(letter_content().model_dump_json())

    generated = generate_cover_letter(
        job(), resume=source, settings=settings(), transport=httpx2.MockTransport(handler)
    )
    assert generated.name == source.name and generated.email == source.email
    assert generated.company == job().company and generated.job_title == job().title
    assert generated.greeting == "Dear Hiring Manager," and generated.closing == "Sincerely,"
    assert all(key not in generated.model_dump_json() for key in ["raw_description", "evidence"])
    assert source.model_dump_json() == before
    with pytest.raises(ValidationError):
        GeneratedCoverLetter.model_validate(
            {**generated.model_dump(), "raw_description": "private"}
        )


@pytest.mark.parametrize("failure", ["missing_description", "oversized", "empty_profile"])
def test_bad_input_skips_request(failure: str) -> None:
    target = job()
    source = resume()
    config = settings()
    if failure == "missing_description":
        target.raw_description = " "
    elif failure == "oversized":
        config.max_document_chars = 10
    else:
        source.education = []
        source.experience = []
        source.projects = []
        source.skills = []

    def handler(_request: httpx2.Request) -> httpx2.Response:
        pytest.fail("Invalid input must not reach the provider")

    with pytest.raises(ValueError):
        generate_cover_letter(
            target, resume=source, settings=config, transport=httpx2.MockTransport(handler)
        )


@pytest.mark.parametrize("failure", ["too_long", "duplicate", "refused"])
def test_invalid_ai_content(failure: str) -> None:
    content = letter_content()
    if failure == "too_long":
        content.paragraphs[1] = "word " * 451
    elif failure == "duplicate":
        content.paragraphs[1] = content.paragraphs[0]
    response = completion(content.model_dump_json())
    if failure == "refused":
        response = httpx2.Response(
            200, json={"choices": [{"message": {"refusal": "No"}, "finish_reason": "stop"}]}
        )
    with pytest.raises(AiCompletionError):
        generate_cover_letter(
            job(),
            resume=resume(),
            settings=settings(),
            transport=httpx2.MockTransport(lambda _request: response),
        )
