import json
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack, nullcontext
from typing import TypeVar

import httpx2
from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

from job_backend.common.ai_schema import completion_schema
from job_backend.common.ai_stream import (
    CompletionStreamError,
    OutputPreview,
    read_completion_stream,
    read_responses_stream,
    responses_completion,
)
from job_backend.common.ai_usage import completion_usage
from job_backend.common.constants import (
    CONNECT_ATTEMPTS,
    CONNECT_RETRY_SECONDS,
    ERROR_PARAMETERS,
    MAX_ERROR_BYTES,
    MAX_RESPONSE_BYTES,
    REASONING_TIMEOUT_SECONDS,
    REPORTED_INPUT,
    REPORTED_OUTPUT,
    REPORTED_SYSTEM_PROMPT,
    SLOW_REASONING_EFFORTS,
)
from job_backend.common.models import (
    AiSettings,
    AiUsage,
    CompletionErrorResponse,
    CompletionOutput,
    CompletionResponse,
    ResponsesBody,
)

Result = TypeVar("Result", bound=BaseModel)


class AiCompletionError(ValueError):
    def __init__(self, message: str, *, details: str | None = None) -> None:
        super().__init__(message)
        if details:
            self.add_note(details)


def complete_json(
    settings: AiSettings,
    *,
    system_prompt: str,
    user_content: str,
    response_model: type[Result],
    schema_name: str,
    transport: httpx2.BaseTransport | None = None,
    client: httpx2.Client | None = None,
    on_usage: Callable[[AiUsage], None] | None = None,
    on_report: Callable[[dict[str, JsonValue]], None] | None = None,
    on_output: Callable[[CompletionOutput], None] | None = None,
) -> Result:
    schema = completion_schema(response_model, strict=settings.response_format == "json_schema")
    instructions = system_prompt + "\nJSON schema: " + json.dumps(schema)
    responses = settings.api == "responses"
    request = (
        _responses_request(settings, instructions, user_content, schema, schema_name)
        if responses
        else _chat_request(settings, instructions, user_content, schema, schema_name)
    )
    url = settings.base_url + ("/responses" if responses else "/chat/completions")
    headers = {"Accept": "application/json"}
    if on_output is not None:
        request["stream"] = True
        if not responses:
            request["stream_options"] = {"include_usage": True}
        headers["Accept"] = "text/event-stream, application/json"
    if settings.api_key is not None:
        headers["Authorization"] = "Bearer " + settings.api_key.get_secret_value()
    usage = completion_usage(settings)
    timeout = request_timeout(settings)
    context = (
        f"Request: POST {url}\n"
        f"Model: {settings.model}\n"
        f"Reasoning effort: {settings.reasoning_effort or 'model default'}\n"
        f"Schema: {schema_name}\n"
        f"Timeout: {timeout:g} seconds"
    )
    chunks: list[bytes] = []
    preview = OutputPreview(on_output, schema_name)
    try:
        completion = _endpoint_completion(
            url,
            request,
            headers,
            responses=responses,
            timeout=timeout,
            transport=transport,
            client=client,
            preview=preview,
            chunks=chunks,
        )
        if completion.usage is not None:
            usage = completion_usage(
                settings, completion.usage.prompt_tokens, completion.usage.completion_tokens
            )
    except AiCompletionError as error:
        error.add_note(context)
        raise
    except (httpx2.ConnectError, httpx2.ConnectTimeout) as error:
        raise AiCompletionError(
            f"Could not reach the AI endpoint after {CONNECT_ATTEMPTS} attempts; "
            "check your network connection",
            details=context,
        ) from error
    except httpx2.HTTPError as error:
        raise AiCompletionError(
            "AI endpoint request failed; check connectivity and timeout", details=context
        ) from error
    except (CompletionStreamError, UnicodeDecodeError) as error:
        raise AiCompletionError(str(error), details=context) from error
    except ValidationError as error:
        body = b"".join(chunks).decode("utf-8", errors="replace")
        raise AiCompletionError(
            "AI endpoint returned an invalid completion envelope",
            details=f"{context}\nResponse body:\n{body}",
        ) from error
    finally:
        try:
            preview.flush()
        finally:
            if on_usage is not None:
                on_usage(usage)
    if on_report:
        try:
            original_input = TypeAdapter(JsonValue).validate_json(user_content)
        except ValidationError:
            original_input = user_content
        output: JsonValue = completion.choices[0].message.content if completion.choices else None
        if isinstance(output, str):
            try:
                output = TypeAdapter(JsonValue).validate_json(output)
            except ValidationError:
                pass
        on_report(
            TypeAdapter(dict[str, JsonValue]).validate_python(
                {
                    "input": original_input,
                    "system_prompt": instructions,
                    "request": _reported_request(request, responses),
                    "response": _reported_response(completion).model_dump(mode="json"),
                    "output": output,
                }
            )
        )
    if len(completion.choices) != 1:
        raise AiCompletionError(
            "AI endpoint must return exactly one completion",
            details=f"{context}\nResponse body:\n{completion.model_dump_json(indent=2)}",
        )
    choice = completion.choices[0]
    if choice.message.refusal or choice.finish_reason != "stop" or not choice.message.content:
        raise AiCompletionError(
            "AI response was refused, incomplete, or empty",
            details=f"{context}\nResponse body:\n{completion.model_dump_json(indent=2)}",
        )
    try:
        return response_model.model_validate_json(choice.message.content, strict=True)
    except ValidationError as error:
        raise AiCompletionError(
            "AI output does not match the requested schema",
            details=f"{context}\nModel output:\n{choice.message.content}",
        ) from error


def _endpoint_completion(
    url: str,
    request: dict[str, JsonValue],
    headers: dict[str, str],
    *,
    responses: bool,
    timeout: float,
    transport: httpx2.BaseTransport | None,
    client: httpx2.Client | None,
    preview: OutputPreview,
    chunks: list[bytes],
) -> CompletionResponse:
    with ExitStack() as stack:
        connection = stack.enter_context(
            nullcontext(client)
            if client is not None
            else httpx2.Client(transport=transport, timeout=timeout)
        )
        response = _open_stream(stack, connection, url, request, headers)
        if not response.is_success:
            raise _endpoint_error(response)
        response_chunks = _response_chunks(response, chunks)
        if response.headers.get("content-type", "").split(";")[0].strip() == "text/event-stream":
            return (
                read_responses_stream(response_chunks, preview)
                if responses
                else read_completion_stream(response_chunks, preview)
            )
        for _chunk in response_chunks:
            pass
        completion = (
            responses_completion(ResponsesBody.model_validate_json(b"".join(chunks), strict=True))
            if responses
            else CompletionResponse.model_validate_json(b"".join(chunks), strict=True)
        )
        if len(completion.choices) == 1:
            preview.append(completion.choices[0].message.content or "")
        return completion


def _chat_request(
    settings: AiSettings,
    instructions: str,
    user_content: str,
    schema: dict[str, JsonValue],
    schema_name: str,
) -> dict[str, JsonValue]:
    request: dict[str, JsonValue] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": user_content},
        ],
    }
    if settings.temperature is not None:
        request["temperature"] = settings.temperature
    if settings.max_output_tokens is not None:
        request["max_completion_tokens"] = settings.max_output_tokens
    if settings.reasoning_effort is not None:
        request["reasoning_effort"] = settings.reasoning_effort
    if settings.response_format == "json_schema":
        request["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "strict": True, "schema": schema},
        }
    elif settings.response_format == "json_object":
        request["response_format"] = {"type": "json_object"}
    return request


def _responses_request(
    settings: AiSettings,
    instructions: str,
    user_content: str,
    schema: dict[str, JsonValue],
    schema_name: str,
) -> dict[str, JsonValue]:
    request: dict[str, JsonValue] = {
        "model": settings.model,
        "instructions": instructions,
        "input": [{"role": "user", "content": user_content}],
        "store": False,
    }
    if settings.temperature is not None:
        request["temperature"] = settings.temperature
    if settings.max_output_tokens is not None:
        request["max_output_tokens"] = settings.max_output_tokens
    reasoning: dict[str, JsonValue] = {}
    if settings.reasoning_effort is not None:
        reasoning["effort"] = settings.reasoning_effort
    if settings.reasoning_summary is not None:
        reasoning["summary"] = settings.reasoning_summary
    if reasoning:
        request["reasoning"] = reasoning
    if settings.response_format == "json_schema":
        request["text"] = {
            "format": {"type": "json_schema", "name": schema_name, "strict": True, "schema": schema}
        }
    elif settings.response_format == "json_object":
        request["text"] = {"format": {"type": "json_object"}}
    return request


def _reported_request(request: dict[str, JsonValue], responses: bool) -> dict[str, JsonValue]:
    if responses:
        return {
            **request,
            "instructions": REPORTED_SYSTEM_PROMPT,
            "input": [{"role": "user", "content": REPORTED_INPUT}],
        }
    return {
        **request,
        "messages": [
            {"role": "system", "content": REPORTED_SYSTEM_PROMPT},
            {"role": "user", "content": REPORTED_INPUT},
        ],
    }


def _reported_response(completion: CompletionResponse) -> CompletionResponse:
    if not completion.choices or completion.choices[0].message.content is None:
        return completion
    first = completion.choices[0]
    message = first.message.model_copy(update={"content": REPORTED_OUTPUT})
    return completion.model_copy(
        update={"choices": [first.model_copy(update={"message": message}), *completion.choices[1:]]}
    )


def request_timeout(settings: AiSettings) -> float:
    if settings.reasoning_effort in SLOW_REASONING_EFFORTS:
        return max(settings.timeout_seconds, REASONING_TIMEOUT_SECONDS)
    return settings.timeout_seconds


def _open_stream(
    stack: ExitStack,
    connection: httpx2.Client,
    url: str,
    request: dict[str, JsonValue],
    headers: dict[str, str],
) -> httpx2.Response:
    for attempt in range(1, CONNECT_ATTEMPTS + 1):
        try:
            return stack.enter_context(
                connection.stream("POST", url, json=request, headers=headers)
            )
        except (httpx2.ConnectError, httpx2.ConnectTimeout):
            if attempt == CONNECT_ATTEMPTS:
                raise
            time.sleep(CONNECT_RETRY_SECONDS * attempt)
    raise RuntimeError("Unreachable connection state")


def _response_chunks(response: httpx2.Response, chunks: list[bytes]) -> Iterator[bytes]:
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise AiCompletionError("AI response exceeds the 4 MiB limit")
        chunks.append(chunk)
        yield chunk


def _endpoint_error(response: httpx2.Response) -> AiCompletionError:
    summary = f"AI endpoint returned HTTP {response.status_code}"
    content = bytearray()
    truncated = False
    for chunk in response.iter_bytes():
        if len(content) + len(chunk) > MAX_ERROR_BYTES:
            content.extend(chunk[: MAX_ERROR_BYTES - len(content)])
            truncated = True
            break
        content.extend(chunk)
    if response.status_code == 400 and not truncated:
        try:
            error = CompletionErrorResponse.model_validate_json(content, strict=True).error
            parameter = ERROR_PARAMETERS.get(error.param or "")
            if parameter is not None:
                summary = f"AI endpoint rejected the {parameter} (HTTP {response.status_code})"
        except ValidationError:
            pass
    body = content.decode(response.encoding or "utf-8", errors="replace")
    if truncated:
        body += f"\n[Response body truncated after {MAX_ERROR_BYTES} bytes]"
    return AiCompletionError(
        summary,
        details=(
            f"HTTP {response.status_code} {response.reason_phrase}\n"
            f"Response headers:\n{json.dumps(dict(response.headers), indent=2)}\n"
            f"Response body:\n{body}"
        ),
    )
