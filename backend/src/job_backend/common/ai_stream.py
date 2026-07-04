import codecs
import time
from collections.abc import Callable, Iterable, Iterator
from uuid import uuid4

from pydantic import JsonValue, TypeAdapter

from job_backend.common.constants import (
    MAX_CONSOLE_OUTPUT_CHARS,
    OUTPUT_INTERVAL_SECONDS,
)
from job_backend.common.models import (
    CompletionChoice,
    CompletionChunk,
    CompletionMessage,
    CompletionOutput,
    CompletionResponse,
    CompletionUsage,
    ResponsesBody,
    ResponsesEvent,
)


class CompletionStreamError(ValueError):
    pass


class OutputPreview:
    def __init__(
        self, callback: Callable[[CompletionOutput], None] | None, schema_name: str = ""
    ) -> None:
        self.callback = callback
        self.schema_name = schema_name
        self.request_id = str(uuid4())
        self.text = ""
        self.reasoning = ""
        self.truncated = False
        self.reasoning_truncated = False
        self.dirty = False
        self.last_emitted: float | None = None

    def append(self, text: str) -> None:
        if not text or self.callback is None:
            return
        self.text += text
        self.truncated = self.truncated or len(self.text) > MAX_CONSOLE_OUTPUT_CHARS
        self.text = self.text[-MAX_CONSOLE_OUTPUT_CHARS:]
        self._changed()

    def restart(self) -> None:
        if self.callback is None or not self.text:
            return
        self.text = ""
        self.truncated = False
        self.dirty = True

    def append_reasoning(self, text: str) -> None:
        if not text or self.callback is None:
            return
        self.reasoning += text
        self.reasoning_truncated = (
            self.reasoning_truncated or len(self.reasoning) > MAX_CONSOLE_OUTPUT_CHARS
        )
        self.reasoning = self.reasoning[-MAX_CONSOLE_OUTPUT_CHARS:]
        self._changed()

    def _changed(self) -> None:
        self.dirty = True
        if (
            self.last_emitted is None
            or time.monotonic() - self.last_emitted >= OUTPUT_INTERVAL_SECONDS
        ):
            self.flush()

    def flush(self) -> None:
        if self.callback is not None and self.dirty:
            self.callback(
                CompletionOutput(
                    request_id=self.request_id,
                    text=_bounded(self.text, self.truncated),
                    reasoning=_bounded(self.reasoning, self.reasoning_truncated),
                    schema_name=self.schema_name,
                )
            )
            self.last_emitted = time.monotonic()
            self.dirty = False


def _bounded(text: str, truncated: bool) -> str:
    prefix = "[Earlier output omitted from console]\n" if truncated else ""
    return prefix + text[-(MAX_CONSOLE_OUTPUT_CHARS - len(prefix)) :]


def read_completion_stream(chunks: Iterable[bytes], preview: OutputPreview) -> CompletionResponse:
    content: list[str] = []
    refusals: list[str] = []
    finish_reason: str | None = None
    usage: CompletionUsage | None = None
    for data in _event_data(chunks):
        if data == "[DONE]":
            if finish_reason is None:
                raise CompletionStreamError("AI stream ended without a completion status")
            return CompletionResponse(
                choices=[
                    CompletionChoice(
                        message=CompletionMessage(
                            content="".join(content), refusal="".join(refusals) or None
                        ),
                        finish_reason=finish_reason,
                    )
                ],
                usage=usage,
            )
        chunk = CompletionChunk.model_validate_json(data, strict=True)
        if chunk.usage is not None:
            usage = chunk.usage
        for choice in chunk.choices:
            if choice.index != 0 or finish_reason is not None:
                raise CompletionStreamError("AI stream returned unexpected completion choices")
            preview.append_reasoning(choice.delta.reasoning_content or choice.delta.reasoning or "")
            if choice.delta.content:
                content.append(choice.delta.content)
                preview.append(choice.delta.content)
            if choice.delta.refusal:
                refusals.append(choice.delta.refusal)
            finish_reason = choice.finish_reason
    raise CompletionStreamError("AI stream was interrupted before completion")


_EVENT = TypeAdapter(dict[str, JsonValue])

_RESPONSES_TEXT = "response.output_text.delta"
_RESPONSES_REFUSAL = "response.refusal.delta"
_RESPONSES_REASONING = {"response.reasoning_summary_text.delta", "response.reasoning_text.delta"}
_RESPONSES_SUMMARY_PART = "response.reasoning_summary_part.added"
_RESPONSES_FINISHED = {"response.completed", "response.incomplete"}
_RESPONSES_READ = {
    _RESPONSES_TEXT,
    _RESPONSES_REFUSAL,
    *_RESPONSES_REASONING,
    _RESPONSES_SUMMARY_PART,
    *_RESPONSES_FINISHED,
    "response.failed",
    "error",
}


def read_responses_stream(chunks: Iterable[bytes], preview: OutputPreview) -> CompletionResponse:
    content: list[str] = []
    refusals: list[str] = []
    summary_parts = 0
    for data in _event_data(chunks):
        if data == "[DONE]":
            continue
        kind = _EVENT.validate_json(data).get("type")
        if not isinstance(kind, str) or kind not in _RESPONSES_READ:
            continue
        event = ResponsesEvent.model_validate_json(data, strict=True)
        if kind == _RESPONSES_TEXT and event.delta:
            content.append(event.delta)
            preview.append(event.delta)
        elif kind == _RESPONSES_REFUSAL and event.delta:
            refusals.append(event.delta)
        elif kind in _RESPONSES_REASONING and event.delta:
            preview.append_reasoning(event.delta)
        elif kind == _RESPONSES_SUMMARY_PART:
            if summary_parts:
                preview.append_reasoning("\n\n")
            summary_parts += 1
        elif kind in _RESPONSES_FINISHED and event.response is not None:
            finished = responses_completion(event.response)
            message = finished.choices[0].message
            return finished.model_copy(
                update={
                    "choices": [
                        finished.choices[0].model_copy(
                            update={
                                "message": CompletionMessage(
                                    content="".join(content) or message.content,
                                    refusal="".join(refusals) or message.refusal,
                                )
                            }
                        )
                    ]
                }
            )
        elif kind == "response.failed":
            error = event.response.error if event.response is not None else None
            raise CompletionStreamError(
                "AI response failed" + (f": {error.message}" if error and error.message else "")
            )
        elif kind == "error":
            raise CompletionStreamError(
                "AI stream reported an error" + (f": {event.message}" if event.message else "")
            )
    raise CompletionStreamError("AI stream was interrupted before completion")


def responses_completion(body: ResponsesBody) -> CompletionResponse:
    texts = [
        part.text
        for item in body.output
        if item.type == "message"
        for part in item.content
        if part.type == "output_text" and part.text
    ]
    refusals = [
        part.refusal
        for item in body.output
        if item.type == "message"
        for part in item.content
        if part.type == "refusal" and part.refusal
    ]
    reason = body.incomplete_details.reason if body.incomplete_details is not None else None
    if body.status == "completed":
        finish = "stop"
    elif body.status == "incomplete":
        finish = "length" if reason == "max_output_tokens" else reason or "incomplete"
    else:
        finish = body.status or "unknown"
    return CompletionResponse(
        choices=[
            CompletionChoice(
                message=CompletionMessage(
                    content="".join(texts), refusal="".join(refusals) or None
                ),
                finish_reason=finish,
            )
        ],
        usage=CompletionUsage(
            prompt_tokens=body.usage.input_tokens, completion_tokens=body.usage.output_tokens
        )
        if body.usage is not None
        else None,
    )


def _event_data(chunks: Iterable[bytes]) -> Iterator[str]:
    decoder = codecs.getincrementaldecoder("utf-8")()
    pending = ""
    data: list[str] = []
    for chunk in chunks:
        pending += decoder.decode(chunk)
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            line = line.removesuffix("\r")
            if not line:
                if data:
                    yield "\n".join(data)
                    data.clear()
            elif line.startswith("data:"):
                data.append(line[5:].removeprefix(" "))
    decoder.decode(b"", final=True)
