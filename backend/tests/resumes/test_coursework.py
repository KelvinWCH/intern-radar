import httpx2
import pytest

from job_backend.common.ai_completion import AiCompletionError
from job_backend.resumes.generate_resume.generate import generate_resume
from job_backend.resumes.generate_resume.models import CourseworkSelection
from job_backend.resumes.models import UserResume
from tests.resumes.helpers import completion, job, resume, selection, settings

COURSES = ["Databases", "Machine Learning", "Operating Systems", "Statistics"]


def with_courses(defaults: list[str], inventory: list[str] = COURSES) -> UserResume:
    source = resume().model_dump()
    source["education"][0]["coursework"] = defaults
    source["education"][0]["available_coursework"] = inventory
    return UserResume.model_validate(source)


@pytest.mark.parametrize(
    "choice",
    [
        CourseworkSelection(source_index=1, course_indices=[]),
        CourseworkSelection(source_index=0, course_indices=[9]),
        CourseworkSelection(source_index=0, course_indices=[1, 1]),
    ],
)
def test_bad_course_choices(choice: CourseworkSelection) -> None:
    draft = selection()
    draft.education_coursework = [choice]
    with pytest.raises(AiCompletionError):
        generate_resume(
            job(),
            resume=with_courses(["Databases"]),
            settings=settings(),
            transport=httpx2.MockTransport(lambda _request: completion(draft.model_dump_json())),
        )
