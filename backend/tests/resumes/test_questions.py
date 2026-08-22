import httpx2
import pytest
from pydantic import JsonValue, TypeAdapter

from job_backend.common.ai_completion import AiCompletionError
from job_backend.persistence.database import Database
from job_backend.profile.models import UserProfile
from job_backend.resumes.questions.answer import answer_question
from job_backend.resumes.questions.models import AnswerContent, AnswerEvidence
from job_backend.resumes.storage import ResumeNotFoundError, load_resume, save_resume
from tests.resumes.helpers import candidate_profile, completion, job, resume, settings


def answer_content() -> AnswerContent:
    return AnswerContent(
        answer="I want to work on your Python APIs and Redis caching. In my internship, "
        "I added Redis caching that reduced p95 latency by 25% in a staging benchmark.",
        missing_information=[],
        evidence=[
            AnswerEvidence(
                source="job", source_index=None, source_quotes=["Build Python APIs, use Redis"]
            ),
            AnswerEvidence(
                source="experience",
                source_index=0,
                source_quotes=[
                    "Added Redis caching that reduced p95 latency by 25% in a staging benchmark."
                ],
            ),
        ],
    )


def test_answer_uses_profile(engine: Database) -> None:
    source = resume()
    save_resume(engine, source)
    question = "Why do you want to work here?"
    extra = "I enjoy improving API response times."

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
        payload = TypeAdapter(dict[str, JsonValue]).validate_json(messages[1]["content"])
        assert UserProfile.model_validate(payload["user_resume"]) == candidate_profile(source)
        assert payload["job"] == job().model_dump(mode="json")
        assert payload["question"] == question
        assert payload["additional_context"] == extra
        assert payload["max_words"] == 100
        return completion(answer_content().model_dump_json())

    result = answer_question(
        question,
        job=job(),
        additional_context=extra,
        max_words=100,
        engine=engine,
        settings=settings(),
        transport=httpx2.MockTransport(handler),
    )
    assert result.question == question and result.answer == answer_content().answer
    assert result.answer is not None and result.word_count == len(result.answer.split())
    assert result.missing_information == []
    assert set(result.model_dump()) == {"question", "answer", "word_count", "missing_information"}
    assert "Internal notes" not in result.model_dump_json()
    assert load_resume(engine) == candidate_profile(source)


@pytest.mark.parametrize(
    ("question", "missing"),
    [
        ("Why do you want to work here?", "Which company and role are you applying for?"),
        ("Are you authorized to work in Canada?", "What is your Canadian work authorization?"),
    ],
)
def test_missing_details_returned(question: str, missing: str) -> None:
    content = AnswerContent(answer=None, missing_information=[missing], evidence=[])
    result = answer_question(
        question,
        resume=resume(),
        settings=settings(),
        transport=httpx2.MockTransport(lambda _request: completion(content.model_dump_json())),
    )
    assert result.answer is None and result.word_count == 0
    assert result.missing_information == [missing]


@pytest.mark.parametrize("failure", ["invented_quote", "cross_entry", "job_as_candidate"])
def test_invalid_evidence(failure: str) -> None:
    content = answer_content()
    evidence = content.evidence[1]
    target = job()
    if failure == "invented_quote":
        evidence.source_quotes = ["Led a team of 50 people"]
    elif failure == "cross_entry":
        evidence.source = "projects"
    elif failure == "job_as_candidate":
        evidence.source_quotes = [target.raw_description]
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return completion(content.model_dump_json())

    with pytest.raises(AiCompletionError, match="could not be verified"):
        answer_question(
            "Tell us about your leadership.",
            job=target,
            resume=resume(),
            settings=settings(),
            transport=httpx2.MockTransport(handler),
        )
    assert calls == 2


def test_missing_profile(engine: Database) -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        pytest.fail("Missing profiles must not reach the provider")

    with pytest.raises(ResumeNotFoundError):
        answer_question(
            "Why here?", engine=engine, settings=settings(), transport=httpx2.MockTransport(handler)
        )
