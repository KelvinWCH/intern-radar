import traceback

import httpx2
import pytest
from pydantic import JsonValue, TypeAdapter

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.ai_schema import completion_schema
from job_backend.resumes.models import ExperienceContext, UserResume
from tests.resumes.helpers import completion, resume, settings


def test_strict_schema() -> None:
    original = UserResume.model_json_schema()
    schema = completion_schema(UserResume, strict=True)
    definitions = TypeAdapter(dict[str, dict[str, JsonValue]]).validate_python(schema["$defs"])
    context = definitions["ExperienceContext"]
    properties = TypeAdapter(dict[str, dict[str, JsonValue]]).validate_python(context["properties"])
    alternatives = TypeAdapter(list[dict[str, JsonValue]]).validate_python(
        properties["company_mission"]["anyOf"]
    )
    assert {"type": "null"} in alternatives
    assert "default" not in properties["company_mission"]
    assert (
        alternatives
        == (original["$defs"]["ExperienceContext"]["properties"]["company_mission"]["anyOf"])
    )
    assert UserResume.model_json_schema() == original
    assert completion_schema(UserResume, strict=False) == original
    assert ExperienceContext().company_mission is None
    assert ExperienceContext().tools == []


@pytest.mark.parametrize("response", [httpx2.Response(200, text="invalid JSON"), completion("{}")])
def test_validation_errors(
    response: httpx2.Response,
) -> None:
    with pytest.raises(AiCompletionError) as caught:
        complete_json(
            settings(),
            system_prompt="Extract JSON",
            user_content="{}",
            response_model=UserResume,
            schema_name="user_resume",
            transport=httpx2.MockTransport(lambda _request: response),
        )
    details = "".join(traceback.format_exception(caught.value))
    assert "ValidationError" in details
    assert (
        "invalid JSON" in details
        if response.text == "invalid JSON"
        else "Model output:\n{}" in details
    )


def test_connection_retry() -> None:
    attempts = 0

    def flaky(request: httpx2.Request) -> httpx2.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx2.ConnectError("[Errno 11004] getaddrinfo failed", request=request)
        return completion(resume().model_dump_json())

    result = complete_json(
        settings(),
        system_prompt="Extract JSON",
        user_content="{}",
        response_model=UserResume,
        schema_name="user_resume",
        transport=httpx2.MockTransport(flaky),
    )
    assert result == resume() and attempts == 3
