import hashlib
import json

from job_backend.scrape.pipeline.models import ScrapedJob


def job_identity_hash(source: str, external_id: str) -> str:
    encoded = json.dumps(["job-v1", source, external_id], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def job_content_hash(job: ScrapedJob) -> str:
    encoded = json.dumps(
        job.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
