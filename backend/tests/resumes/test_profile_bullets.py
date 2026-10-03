from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from job_backend.main import create_app
from job_backend.resumes.profile.models import ResumeProfileState
from tests.resumes.helpers import (
    resume,
)


@pytest.mark.parametrize("section", ["education", "experience"])
@pytest.mark.parametrize("invalid_bullets", ["First bullet\nSecond bullet", [""]])
def test_invalid_bullets_rejected(tmp_path: Path, section: str, invalid_bullets: JsonValue) -> None:
    source = resume()
    with TestClient(create_app(tmp_path / "postgres")) as client:
        assert (
            client.put(
                "/resumes/manager", json={"resume": source.model_dump(), "revision": 0}
            ).status_code
            == 200
        )
        invalid = TypeAdapter(dict[str, JsonValue]).validate_json(source.model_dump_json())
        entries = TypeAdapter(list[dict[str, JsonValue]]).validate_python(invalid[section])
        entries[0]["bullets"] = invalid_bullets
        invalid[section] = list[JsonValue](entries)
        response = client.put("/resumes/manager", json={"resume": invalid, "revision": 1})
        assert response.status_code == 422
        saved = ResumeProfileState.model_validate_json(client.get("/resumes/manager").content)
        assert saved.resume == source and saved.revision == 1
