from pydantic import JsonValue

from job_backend.common.ai_completion import AiCompletionError
from job_backend.jobs.models import TailoringJob
from job_backend.resumes.models import UserResume
from job_backend.resumes.questions.models import AnswerEvidence


def _strings(value: JsonValue) -> list[str]:
    if isinstance(value, str):
        return [" ".join(value.split())]
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    return []


def validate_evidence(
    evidence_items: list[AnswerEvidence],
    resume: UserResume,
    job: TailoringJob | None,
    additional_context: str | None,
) -> None:
    sources: dict[str, list[list[str]]] = {
        "profile": [
            _strings(
                resume.model_dump(
                    mode="json",
                    exclude={
                        "experience",
                        "projects",
                        "education",
                        "skills",
                        "additional_sections",
                    },
                )
            )
        ],
        "job": [_strings(job.model_dump(mode="json"))] if job is not None else [],
        "additional_context": [_strings(additional_context)]
        if additional_context is not None
        else [],
        **{
            name: [_strings(entry.model_dump(mode="json")) for entry in entries]
            for name, entries in (
                ("experience", resume.experience),
                ("projects", resume.projects),
                ("education", resume.education),
                ("skills", resume.skills),
                ("additional_sections", resume.additional_sections),
            )
        },
    }
    for evidence in evidence_items:
        index = evidence.source_index
        if evidence.source in {"profile", "job", "additional_context"}:
            if index is not None:
                raise AiCompletionError("AI question evidence must use null for unindexed sources")
            index = 0
        entries = sources[evidence.source]
        if index is None or index < 0 or index >= len(entries):
            raise AiCompletionError("AI question evidence references an unknown entry")
        if any(
            not any(" ".join(quote.split()) in source for source in entries[index])
            for quote in evidence.source_quotes
        ):
            raise AiCompletionError("AI question evidence does not belong to its source entry")
