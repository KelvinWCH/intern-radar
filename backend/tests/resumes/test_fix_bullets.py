import json

import httpx2

from job_backend.resumes.compile_pdf.models import CompiledPdf, PdfCompiler
from job_backend.resumes.generate_resume.fix_bullets import fix_flagged_bullets
from job_backend.resumes.models import GeneratedResume
from tests.resumes.helpers import completion, resume, settings
from tests.resumes.pdf_helpers import pdf_bytes
from tests.resumes.test_render import generated_resume

DANGLE = "JOB-RESUME-DANGLE: experience-0-0 30.0pt"


def compiles(*logs: str) -> PdfCompiler:
    queue = iter(logs)
    return lambda _source: CompiledPdf(pdf=pdf_bytes(), log=next(queue))


def document() -> GeneratedResume:
    draft = generated_resume()
    draft.experience[0].bullets = [
        "Cut p95 latency 25% for Python APIs by adding Redis caching in a staging benchmark run",
        "Built Python APIs used by the checkout team",
    ]
    return draft


def transport(fixes: list[dict[str, str]], requests: list[bytes]) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request.content)
        return completion(json.dumps({"bullets": fixes}))

    return httpx2.MockTransport(handler)


def test_flagged_bullet_rewritten() -> None:
    requests: list[bytes] = []
    result = fix_flagged_bullets(
        document(),
        resume(),
        settings(),
        compiler=compiles(DANGLE, ""),
        transport=transport(
            [{"line_id": "experience-0-0", "text": "Cut p95 latency 25% with Redis caching"}],
            requests,
        ),
    )
    assert result is not None
    fixed, pdf, remaining = result
    assert fixed.experience[0].bullets[0] == "Cut p95 latency 25% with Redis caching"
    assert fixed.experience[0].bullets[1] == "Built Python APIs used by the checkout team"
    assert remaining == 0 and pdf
    sent = json.loads(json.loads(requests[0])["messages"][1]["content"])
    assert sent["bullets"][0]["sibling_bullets_already_said"] == [
        "Built Python APIs used by the checkout team"
    ]
    assert "Redis caching" in sent["bullets"][0]["source_text"]
    assert "spills only a few words" in sent["bullets"][0]["problem"]


def test_bad_fix_not_kept() -> None:
    for text in (
        "Cut latency by a third with Redis caching",
        "Built Python APIs used by the checkout team daily",
    ):
        assert (
            fix_flagged_bullets(
                document(),
                resume(),
                settings(),
                compiler=compiles(DANGLE, ""),
                transport=transport([{"line_id": "experience-0-0", "text": text}], []),
            )
            is None
        )
