import httpx2
import pytest

from job_backend.common.ai_completion import AiCompletionError
from job_backend.resumes.generate_resume.generate import generate_resume
from job_backend.resumes.generate_resume.models import (
    EntrySelection,
    SupportedBullet,
    TailoredContent,
)
from job_backend.resumes.models import GeneratedResume, UserResume
from tests.resumes.helpers import (
    completion,
    job,
    resume,
    selection,
    settings,
)

MINIMUM = {"experience": 3, "projects": 2}


def entry_with(section: str, count: int) -> tuple[UserResume, TailoredContent, EntrySelection]:
    source = resume()
    draft = selection()
    entry = source.experience[0] if section == "experience" else source.projects[0]
    selected = draft.experience[0] if section == "experience" else draft.projects[0]
    entry.bullets = [f"Built feature {index}." for index in range(count)]
    selected.bullets = [
        SupportedBullet(source_bullet=i, text=text) for i, text in enumerate(entry.bullets)
    ]
    return source, draft, selected


def tailor(source: UserResume, draft: TailoredContent) -> GeneratedResume:
    return generate_resume(
        job(),
        resume=source,
        settings=settings(),
        transport=httpx2.MockTransport(lambda _request: completion(draft.model_dump_json())),
    )


@pytest.mark.parametrize("section", ["experience", "projects"])
def test_too_few_bullets_rejected(section: str) -> None:
    source, draft, selected = entry_with(section, MINIMUM[section] + 1)
    del selected.bullets[-2:]
    with pytest.raises(AiCompletionError, match=f"at least {MINIMUM[section]} bullets"):
        tailor(source, draft)


@pytest.mark.parametrize("section", ["experience", "projects"])
def test_entries_cannot_be_dropped(section: str) -> None:
    source, draft, _selected = entry_with(section, MINIMUM[section])
    if section == "experience":
        draft.experience = []
    else:
        draft.projects = []
    with pytest.raises(AiCompletionError, match="every original"):
        tailor(source, draft)
