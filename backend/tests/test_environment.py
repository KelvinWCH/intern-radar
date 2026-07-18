from pathlib import Path

from pytest import MonkeyPatch

from job_backend.common.models import AiSettings


def test_dotenv_loading(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / ".env").write_text(
        "JOB_AI_BASE_URL=https://api.openai.com/v1\nJOB_AI_MODEL=gpt-6-luna\n"
        "JOB_AI_API_KEY=fictional-secret\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for name in ("JOB_AI_BASE_URL", "JOB_AI_MODEL", "JOB_AI_API_KEY", "JOB_AI_REASONING_EFFORT"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    monkeypatch.setenv("JOB_AI_MODEL", "explicit-model")
    settings = AiSettings.from_environment()
    assert settings.model == "explicit-model"
    assert settings.base_url == "https://api.openai.com/v1"
    assert settings.api_key is not None and "fictional-secret" not in repr(settings)
    assert settings.reasoning_effort is None
    monkeypatch.setenv("JOB_AI_REASONING_EFFORT", "high")
    assert AiSettings.from_environment().reasoning_effort == "high"
