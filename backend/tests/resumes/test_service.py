import httpx2
import pytest
from pydantic import JsonValue, TypeAdapter

from job_backend.common.ai_completion import AiCompletionError
from job_backend.persistence.database import Database
from job_backend.profile.models import UserProfile
from job_backend.resumes.generate_resume.generate import generate_resume
from job_backend.resumes.generate_resume.models import (
    EntrySelection,
    SupportedBullet,
)
from job_backend.resumes.render_latex.render import resume_to_latex
from job_backend.resumes.storage import load_resume, save_resume
from tests.resumes.helpers import candidate_profile, completion, job, resume, selection, settings


def test_tailoring_uses_raw_details(engine: Database) -> None:
    original = resume()
    save_resume(engine, original)

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
        payload = TypeAdapter(dict[str, JsonValue]).validate_json(messages[1]["content"])
        supplied = UserProfile.model_validate(payload["user_resume"])
        assert supplied == candidate_profile(original)
        assert payload["job"] == job().model_dump(mode="json")
        assert "raw_description" in messages[0]["content"]
        assert "never move facts" in messages[0]["content"].lower()
        assert payload["candidate_instructions"] == "Emphasize backend performance work."
        return completion(selection().model_dump_json())

    generated = generate_resume(
        job(),
        engine=engine,
        settings=settings(),
        transport=httpx2.MockTransport(handler),
        instructions="  Emphasize backend performance work.  ",
    )
    assert "raw_description" not in generated.model_dump_json()
    assert generated.experience[0].company == original.experience[0].company
    latex = resume_to_latex(generated)
    assert r"\begin{document}" in latex and latex.endswith("\\end{document}\n")
    assert r"25\%" in latex and r"500}{ search queries" in latex
    assert "Built Python APIs." in latex and "Built a search service." in latex
    assert ":} Python, Redis, TypeScript\n" in latex
    assert "Department scholarship" in latex
    assert r"BSc in Computer Science | GPA: 3.8/4.0}" in latex
    assert r"Example \& Co" in latex and r"Search\_Project" in latex
    assert "Internal notes" not in latex
    assert load_resume(engine) == candidate_profile(original)


@pytest.mark.parametrize("failure", ["entry", "duplicate", "unknown_bullet"])
def test_invalid_selections(failure: str) -> None:
    result = selection()
    if failure == "entry":
        result.experience = [
            EntrySelection(
                source_index=42,
                bullets=[SupportedBullet(source_bullet=None, text="Invented")],
            )
        ]
    elif failure == "duplicate":
        result.experience *= 2
    elif failure == "unknown_bullet":
        result.experience[0].bullets[0].source_bullet = 42
    with pytest.raises(AiCompletionError):
        generate_resume(
            job(),
            resume=resume(),
            settings=settings(),
            transport=httpx2.MockTransport(lambda _request: completion(result.model_dump_json())),
        )
