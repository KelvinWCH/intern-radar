from pathlib import Path

import httpx2
from fastapi.testclient import TestClient
from pydantic import JsonValue, TypeAdapter

from job_backend.main import create_app
from job_backend.resumes.dependencies import resume_ai_settings
from job_backend.resumes.models import GeneratedResume, UserResume
from job_backend.resumes.render_latex.models import LatexResume
from tests.resumes.helpers import completion, job, resume, selection, settings


def test_resume_stages(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal calls
        calls += 1
        body = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        messages = TypeAdapter(list[dict[str, str]]).validate_python(body["messages"])
        if calls == 1:
            return completion(resume().model_dump_json())
        assert "Extra detail added after upload" in messages[1]["content"]
        return completion(selection().model_dump_json())

    app = create_app(tmp_path / "postgres", resume_transport=httpx2.MockTransport(handler))
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        assert client.get("/resumes/profile").status_code == 404
        assert client.post("/resumes/generate", json=job().model_dump()).status_code == 409
        response = client.post("/resumes/upload", files={"file": ("resume.txt", b"Alex Example")})
        assert response.status_code == 200
        profile = UserResume.model_validate_json(response.content)
        profile.projects[0].raw_description += " Extra detail added after upload."
        assert client.put("/resumes/profile", json=profile.model_dump()).status_code == 200
        response = client.post("/resumes/generate", json=job().model_dump())
        assert response.status_code == 200
        generated = GeneratedResume.model_validate_json(response.content)
        assert "raw_description" not in generated.model_dump_json()
        rendered = client.post("/resumes/latex", json=generated.model_dump())
        assert rendered.status_code == 200
        assert r"25\%" in LatexResume.model_validate_json(rendered.content).latex
        assert UserResume.model_validate_json(client.get("/resumes/profile").content) == profile
        assert client.post("/resumes/latex", json=profile.model_dump()).status_code == 422
        assert client.get("/openapi.json").status_code == 200
    assert calls == 2


def test_failed_upload_keeps_profile(
    tmp_path: Path,
) -> None:
    transport = httpx2.MockTransport(lambda _request: httpx2.Response(429, text="private data"))
    app = create_app(tmp_path / "postgres", resume_transport=transport)
    app.dependency_overrides[resume_ai_settings] = settings
    with TestClient(app) as client:
        client.put("/resumes/profile", json=resume().model_dump())
        failed = client.post("/resumes/upload", files={"file": ("resume.txt", b"Alex Example")})
        assert failed.status_code == 502 and "private data" not in failed.text
        invalid = client.post("/resumes/upload", files={"file": ("resume.exe", b"invalid")})
        assert invalid.status_code == 422
        assert UserResume.model_validate_json(client.get("/resumes/profile").content) == resume()
