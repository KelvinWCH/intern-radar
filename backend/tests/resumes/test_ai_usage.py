import httpx2
import pytest
from pydantic import JsonValue, SecretStr, TypeAdapter

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.ai_usage import AiUsageTracker
from job_backend.common.models import AiModelOptions, AiSettings
from job_backend.resumes.generate_resume.models import TailoredContent
from tests.resumes.helpers import selection


def ai_settings() -> AiSettings:
    return AiSettings(
        base_url="http://localhost:1234/v1",
        model="fictional",
        api_key=SecretStr("private-key"),
    )


def response(content: str, *, finish: str = "stop", usage: bool = True) -> httpx2.Response:
    body: dict[str, JsonValue] = {
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 1000, "completion_tokens": 250, "total_tokens": 1250}
    return httpx2.Response(200, json=body)


@pytest.mark.parametrize("finish", ["stop", "length"])
def test_usage_recorded_on_incomplete(finish: str) -> None:
    config = AiModelOptions(temperature=0, max_output_tokens=900, reasoning_effort="xhigh").apply(
        ai_settings()
    )
    tracker = AiUsageTracker(config)

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        assert body["model"] == "fictional"
        assert body["temperature"] == 0 and body["max_completion_tokens"] == 900
        assert body["reasoning_effort"] == "xhigh"
        return response(selection().model_dump_json(), finish=finish)

    def call() -> TailoredContent:
        return complete_json(
            config,
            system_prompt="Test",
            user_content="Test",
            response_model=TailoredContent,
            schema_name="test",
            transport=httpx2.MockTransport(handler),
            on_usage=tracker.record,
        )

    if finish == "stop":
        assert call() == selection()
    else:
        with pytest.raises(AiCompletionError):
            call()
    usage = tracker.snapshot()
    assert usage.input_tokens == 1000 and usage.output_tokens == 250 and usage.calls == 1
