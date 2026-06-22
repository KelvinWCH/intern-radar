from pathlib import Path

from fastapi.testclient import TestClient

from job_backend.main import create_app
from job_backend.profile.models import CandidateAnswer, CandidateStory, UserProfileState
from tests.resumes.helpers import candidate_profile


def test_profile_roundtrip(tmp_path: Path) -> None:
    profile = candidate_profile()
    profile.stories = [CandidateStory(title="Caching decision", action="Compared Redis options")]
    profile.answers = [CandidateAnswer(question="Why backend?", answer="I enjoy building APIs")]
    profile.preferences.graduation_year = 2028
    profile.resume_settings.min_experience_bullets = 4
    profile.experience[0].context.company_mission = "Make analytics accessible"
    profile.experience[0].context.contribution = "Designed the API"
    with TestClient(create_app(tmp_path / "profile")) as client:
        assert client.get("/profile").json()["profile"] is None
        saved = client.put("/profile", json={"profile": profile.model_dump(), "revision": 0})
        assert saved.status_code == 200, saved.text
        state = UserProfileState.model_validate_json(saved.content)
        assert state.profile == profile and state.revision == 1
        assert (
            client.put(
                "/profile", json={"profile": profile.model_dump(), "revision": 0}
            ).status_code
            == 409
        )
        legacy = profile.model_dump(
            exclude={"stories", "answers", "preferences", "about", "goals", "resume_settings"}
        )
        legacy["name"] = "Alex Updated"
        assert (
            client.put("/resumes/manager", json={"resume": legacy, "revision": 1}).status_code
            == 200
        )
        updated = UserProfileState.model_validate_json(client.get("/profile").content)
        assert updated.profile is not None
        assert updated.profile.stories == profile.stories
        assert updated.profile.answers == profile.answers
        assert updated.profile.preferences == profile.preferences
        assert updated.profile.resume_settings.min_experience_bullets == 4
        assert updated.profile.experience[0].context == profile.experience[0].context
        assert updated.profile.name == "Alex Updated"
