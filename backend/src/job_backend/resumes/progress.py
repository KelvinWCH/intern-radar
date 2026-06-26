from job_backend.resumes.models import GenerationStage, ProgressCallback


def report_progress(
    callback: ProgressCallback | None, stage: GenerationStage, message: str
) -> None:
    if callback is not None:
        callback(stage, message)
