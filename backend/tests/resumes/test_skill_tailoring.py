import httpx2
import pytest

from job_backend.common.ai_completion import AiCompletionError
from job_backend.resumes.generate_resume.generate import generate_resume
from job_backend.resumes.generate_resume.models import SkillSelection
from job_backend.resumes.generate_resume.skills import tailor_skills
from job_backend.resumes.models import SkillGroup
from tests.resumes.helpers import completion, job, resume, selection, settings


def test_relevant_skills_first() -> None:
    source = resume()
    source.skills[0].available_items += ["Docker", "OpenTelemetry"]
    before = source.model_dump_json()
    draft = selection()
    draft.skill_selections = [SkillSelection(group_index=0, item_indices=[4, 3, 1])]
    result = generate_resume(
        job(),
        resume=source,
        settings=settings(),
        transport=httpx2.MockTransport(lambda _request: completion(draft.model_dump_json())),
    )
    assert result.skills == [
        SkillGroup(
            category="Languages & tools",
            items=["OpenTelemetry", "Docker", "Redis", "Python", "TypeScript"],
        )
    ]
    assert "available_items" not in result.model_dump_json()
    assert source.model_dump_json() == before


@pytest.mark.parametrize("group_index,indices", [(99, [0]), (0, [99]), (0, [0, 0])])
def test_bad_skill_choices(group_index: int, indices: list[int]) -> None:
    draft = selection()
    draft.skill_selections = [SkillSelection(group_index=group_index, item_indices=indices)]
    with pytest.raises(AiCompletionError):
        tailor_skills(resume(), draft)
