import json

import httpx2
import pytest

from job_backend.common.ai_completion import AiCompletionError
from job_backend.resumes.generate_resume.generate import generate_resume
from tests.resumes.helpers import completion, job, resume, selection, settings


def test_summary_output_is_invalid() -> None:
    result = selection()
    generated = generate_resume(
        job(),
        resume=resume(),
        settings=settings(),
        transport=httpx2.MockTransport(lambda _request: completion(result.model_dump_json())),
    )
    assert "summary" not in generated.model_dump()
    invalid = json.dumps({**result.model_dump(), "summary": "Unrequested summary"})
    with pytest.raises(AiCompletionError, match="schema"):
        generate_resume(
            job(),
            resume=resume(),
            settings=settings(),
            transport=httpx2.MockTransport(lambda _request: completion(invalid)),
        )
