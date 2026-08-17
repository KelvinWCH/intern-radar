import httpx2
import pytest

from job_backend.common.ai_completion import AiCompletionError
from job_backend.resumes.generate_resume.generate import generate_resume
from job_backend.resumes.generate_resume.models import ProjectTechnologySelection
from tests.resumes.helpers import (
    completion,
    job,
    resume,
    selection,
    settings,
)


@pytest.mark.parametrize("project_index,indices", [(0, [999]), (1, [0]), (0, [0, 0])])
def test_invalid_tech_choices(project_index: int, indices: list[int]) -> None:
    source = resume()
    draft = selection()
    draft.project_technologies = [
        ProjectTechnologySelection(source_index=project_index, technology_indices=indices)
    ]
    with pytest.raises(AiCompletionError):
        generate_resume(
            job(),
            resume=source,
            settings=settings(),
            transport=httpx2.MockTransport(lambda _request: completion(draft.model_dump_json())),
        )
