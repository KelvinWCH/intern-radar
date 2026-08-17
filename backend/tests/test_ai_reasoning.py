import json
from collections.abc import Iterator

import httpx2
from pydantic import BaseModel, JsonValue, TypeAdapter

from job_backend.common.ai_completion import complete_json
from job_backend.common.constants import REPORTED_INPUT, REPORTED_SYSTEM_PROMPT
from job_backend.common.models import AiSettings, AiUsage, CompletionOutput
from tests.resumes.helpers import settings


class Draft(BaseModel):
    text: str


def responses_settings() -> AiSettings:
    return settings().model_copy(
        update={"api": "responses", "reasoning_summary": "auto", "reasoning_effort": "high"}
    )


def event(payload: dict[str, JsonValue]) -> bytes:
    return f"event: {payload['type']}\ndata: {json.dumps(payload)}\n\n".encode()


def finished(status: str = "completed", **extra: JsonValue) -> bytes:
    body: dict[str, JsonValue] = {
        "status": status,
        "output": [
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Plan"}]},
            {"type": "message", "content": [{"type": "output_text", "text": '{"text":"hi"}'}]},
        ],
        "usage": {"input_tokens": 30, "output_tokens": 12},
        **extra,
    }
    return event({"type": f"response.{status}", "response": body})


def stream(*events: bytes) -> httpx2.Response:
    class Events(httpx2.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield from events

    return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Events())


def test_reasoning_stream() -> None:
    seen: dict[str, JsonValue] = {}
    usages: list[AiUsage] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path.endswith("/responses")
        seen.update(TypeAdapter(dict[str, JsonValue]).validate_json(request.content))
        return stream(
            event({"type": "response.created", "response": {"status": "in_progress"}}),
            event({"type": "response.reasoning_summary_part.added", "summary_index": 0}),
            event({"type": "response.reasoning_summary_text.delta", "delta": "**Reading** it"}),
            event({"type": "response.reasoning_summary_part.added", "summary_index": 1}),
            event({"type": "response.reasoning_summary_text.delta", "delta": "Then writing"}),
            event({"type": "response.output_text.delta", "delta": '{"text":'}),
            event({"type": "response.output_text.delta", "delta": '"hi"}'}),
            finished(),
        )

    outputs: list[CompletionOutput] = []
    reports: list[dict[str, JsonValue]] = []
    result = complete_json(
        responses_settings(),
        system_prompt="Return JSON",
        user_content='{"job":"x"}',
        response_model=Draft,
        schema_name="draft",
        transport=httpx2.MockTransport(handler),
        on_output=outputs.append,
        on_usage=usages.append,
        on_report=reports.append,
    )
    assert result.text == "hi"
    report = reports[0]
    assert report["input"] == {"job": "x"} and report["output"] == {"text": "hi"}
    request = TypeAdapter(dict[str, JsonValue]).validate_python(report["request"])
    assert request["instructions"] == REPORTED_SYSTEM_PROMPT
    assert request["input"] == [{"role": "user", "content": REPORTED_INPUT}]
    assert request["reasoning"] == {"effort": "high", "summary": "auto"}
    assert outputs[-1].reasoning == "**Reading** it\n\nThen writing"
    assert outputs[-1].text == '{"text":"hi"}'
    assert usages[-1].input_tokens == 30 and usages[-1].output_tokens == 12
    assert seen["reasoning"] == {"effort": "high", "summary": "auto"}
    assert seen["store"] is False and seen["stream"] is True
    assert seen["input"] == [{"role": "user", "content": '{"job":"x"}'}]
    instructions = seen["instructions"]
    assert isinstance(instructions, str) and instructions.startswith("Return JSON")
    text = TypeAdapter(dict[str, JsonValue]).validate_python(seen["text"])
    assert TypeAdapter(dict[str, JsonValue]).validate_python(text["format"])["name"] == "draft"
    assert "messages" not in seen and "stream_options" not in seen
