import hashlib
import json

from job_backend.jobs.urls import canonical_job_url


def job_document_id(source: str, external_id: str, application_url: str | None = None) -> str:
    if not source or not external_id:
        raise ValueError("A job needs a source and external identity")
    values = (
        ("manual-url-v1", canonical_job_url(application_url))
        if source == "user" and application_url
        else ("manual-text-v1", external_id)
        if source == "user"
        else ("listing-v1", source, external_id)
    )
    encoded = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()
    return "job-" + hashlib.sha256(encoded).hexdigest()


def next_manual_url_id(previous_id: str) -> str:
    encoded = json.dumps(("manual-url-reuse-v1", previous_id), separators=(",", ":")).encode()
    return "job-" + hashlib.sha256(encoded).hexdigest()
