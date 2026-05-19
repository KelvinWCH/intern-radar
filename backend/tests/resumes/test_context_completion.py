import json

import httpx2
import pytest
from pydantic import JsonValue

from job_backend.common.ai_completion import AiCompletionError
from job_backend.persistence.database import Database
from job_backend.resumes.questions.complete import complete_context
from job_backend.resumes.questions.models import ContextCompletionRequest
from job_backend.resumes.storage import save_resume
from tests.resumes.helpers import completion, resume, settings


@pytest.mark.parametrize("failure", ["missing_evidence", "wrong_quote", "too_long"])
def test_unsafe_suggestions_rejected(engine: Database, failure: str) -> None:
    save_resume(engine, resume())
    data: dict[str, JsonValue] = {
        "continuation": " use Python.",
        "evidence": [{"source": "skills", "source_index": 0, "source_quotes": ["Python"]}],
    }
    if failure == "missing_evidence":
        data["evidence"] = []
    elif failure == "wrong_quote":
        data["evidence"] = [{"source": "skills", "source_index": 0, "source_quotes": ["Rust"]}]
    elif failure == "too_long":
        data["continuation"] = "word " * 61
    else:
        data["continuation"] = " use\nPython."
    calls = 0

    def handler(_request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        return completion(json.dumps(data))

    with pytest.raises(AiCompletionError):
        complete_context(
            ContextCompletionRequest(text="I", purpose="context"),
            engine,
            settings(),
            transport=httpx2.MockTransport(handler),
        )
    assert calls == 1
