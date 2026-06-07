from pathlib import Path

from job_backend.scrape.worker.models import WorkerState


def load_state(path: Path) -> WorkerState:
    if not path.exists():
        return WorkerState()
    return WorkerState.model_validate_json(path.read_bytes(), strict=True)


def save_state(path: Path, state: WorkerState) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)
