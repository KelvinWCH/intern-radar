from collections.abc import Iterator

import httpx2
import pytest
from pydantic import BaseModel, JsonValue, TypeAdapter
from pytest import MonkeyPatch

from job_backend.common.ai_completion import AiCompletionError, complete_json
from job_backend.common.constants import (
    MAX_RESPONSE_BYTES,
    REPORTED_INPUT,
    REPORTED_OUTPUT,
    REPORTED_SYSTEM_PROMPT,
)
from job_backend.common.models import AiUsage, CompletionOutput
from tests.resumes.helpers import completion_event, settings


class Draft(BaseModel):
    text: str


def test_streamed_content(monkeypatch: MonkeyPatch) -> None:
    outputs: list[CompletionOutput] = []
    usages: list[AiUsage] = []
    reports: list[dict[str, JsonValue]] = []
    clock = [1.0]
    monkeypatch.setattr("job_backend.common.ai_stream.time.monotonic", lambda: clock[0])

    class Stream(httpx2.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            yield b": keepalive\r\n\r\n"
            first = completion_event('{"text":"café')
            split = first.index(b"\xc3") + 1
            yield first[:split]
            assert not outputs
            yield first[split:]
            assert [output.text for output in outputs] == ['{"text":"café']
            yield completion_event(" tools")
            assert len(outputs) == 1
            clock[0] = 2.1
            yield completion_event(" today")
            assert len(outputs) == 2 and outputs[-1].text == '{"text":"café tools today'
            yield completion_event('"}')
            yield completion_event(finish="stop")
            yield b'data: {"choices":[],"usage":{"prompt_tokens":12,"completion_tokens":8}}\n\n'
            yield b"data: [DONE]\n\n"

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert b'"stream":true' in request.content
        assert b'"include_usage":true' in request.content
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, stream=Stream())

    result = complete_json(
        settings(),
        system_prompt="Return JSON",
        user_content="{}",
        response_model=Draft,
        schema_name="draft",
        transport=httpx2.MockTransport(handler),
        on_output=outputs.append,
        on_usage=usages.append,
        on_report=reports.append,
    )
    assert result.text == "café tools today"
    assert [output.text for output in outputs] == [
        '{"text":"café',
        '{"text":"café tools today',
        '{"text":"café tools today"}',
    ]
    assert len({output.request_id for output in outputs}) == 1
    assert usages[0].input_tokens == 12 and usages[0].output_tokens == 8
    assert reports[0]["output"] == {"text": "café tools today"}
    report = TypeAdapter(dict[str, JsonValue]).validate_python(reports[0])
    assert report["input"] == {} and str(report["system_prompt"]).startswith("Return JSON")
    assert TypeAdapter(dict[str, JsonValue]).validate_python(report["request"])["messages"] == [
        {"role": "system", "content": REPORTED_SYSTEM_PROMPT},
        {"role": "user", "content": REPORTED_INPUT},
    ]
    assert "café" not in str(report["response"]) and REPORTED_OUTPUT in str(report["response"])


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (completion_event('{"text":"partial'), "interrupted"),
        (completion_event('{"text":"ok"}', finish="length") + b"data: [DONE]\n\n", "incomplete"),
        (b":" + b"x" * MAX_RESPONSE_BYTES, "4 MiB"),
    ],
    ids=["disconnect", "missing-status", "length"],
)
def test_invalid_stream(body: bytes, error: str) -> None:
    outputs: list[CompletionOutput] = []
    with pytest.raises(AiCompletionError, match=error):
        complete_json(
            settings(),
            system_prompt="Return JSON",
            user_content="{}",
            response_model=Draft,
            schema_name="draft",
            transport=httpx2.MockTransport(
                lambda _request: httpx2.Response(
                    200, headers={"content-type": "text/event-stream"}, content=body
                )
            ),
            on_output=outputs.append,
        )
    if error == "interrupted":
        assert outputs[-1].text == '{"text":"partial'
