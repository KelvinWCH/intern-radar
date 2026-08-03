import json

import httpx2
import pytest
from pydantic import JsonValue, SecretStr, TypeAdapter

from job_backend.common.models import AiSettings
from job_backend.scrape.errors import SourceDataError
from job_backend.scrape.pipeline.ai import AiNormalizer
from job_backend.scrape.pipeline.models import (
    RawDocument,
)
from tests.helpers import StubNormalizer, listing


def test_schema_request() -> None:
    document = RawDocument(
        content=json.dumps(listing()),
        source_url="https://example.com/jobs",
        media_type="application/json",
    )
    result = StubNormalizer().extract(document)

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert str(request.url) == "http://localhost:1234/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer fictional-key"
        data = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        assert data["model"] == "configured-model"
        response_format = data["response_format"]
        assert isinstance(response_format, dict)
        assert response_format["type"] == "json_schema"
        messages = data["messages"]
        assert isinstance(messages, list) and len(messages) == 2
        return httpx2.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": result.model_dump_json()}, "finish_reason": "stop"}
                ]
            },
        )

    normalizer = AiNormalizer(
        AiSettings(
            base_url="http://localhost:1234/v1/",
            model="configured-model",
            api_key=SecretStr("fictional-key"),
        ),
        httpx2.MockTransport(handler),
    )
    assert normalizer.extract(document) == result
    assert "fictional-key" not in repr(normalizer.settings)


def test_cache_keys() -> None:
    document = RawDocument(content="Posted yesterday", source_url="https://example.com/job")
    requests: list[dict[str, JsonValue]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        requests.append(body)
        messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
        assert RawDocument.model_validate_json(messages[-1]["content"]) == document
        assert (
            'Relative-only dates such as "yesterday" or "2 days ago" must stay null'
            in (messages[0]["content"])
        )
        return httpx2.Response(
            200,
            json={"choices": [{"message": {"content": '{"jobs": []}'}, "finish_reason": "stop"}]},
        )

    settings = AiSettings(base_url="http://localhost/v1", model="local")
    first = AiNormalizer(settings, httpx2.MockTransport(handler))
    second = AiNormalizer(settings, httpx2.MockTransport(handler))
    assert first.cache_key == second.cache_key
    first.extract(document)
    second.extract(document)
    assert len(requests) == 2 and requests[0] == requests[1]


@pytest.mark.parametrize(
    ("content", "reason", "refusal"),
    [
        ('{"jobs": []}', "length", None),
        ('{"jobs": []}', "stop", "refused"),
        ("not JSON", "stop", None),
        ('{"jobs": [{"company": "invented"}]}', "stop", None),
    ],
)
def test_bad_output_rejected(content: str, reason: str, refusal: str | None) -> None:
    transport = httpx2.MockTransport(
        lambda _request: httpx2.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": content, "refusal": refusal}, "finish_reason": reason}
                ]
            },
        )
    )
    normalizer = AiNormalizer(AiSettings(base_url="http://localhost/v1", model="local"), transport)
    with pytest.raises(SourceDataError):
        normalizer.extract(RawDocument(content="raw data", source_url="https://example.com"))
