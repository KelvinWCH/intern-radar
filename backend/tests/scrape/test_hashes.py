from job_backend.scrape.utils.hashes import job_content_hash, job_identity_hash
from tests.helpers import normalized_listing


def test_identity_hash() -> None:
    assert job_identity_hash("a:b", "c") != job_identity_hash("a", "b:c")
    assert job_identity_hash("first", "same-id") != job_identity_hash("second", "same-id")
    assert job_identity_hash("first", "same-id") == job_identity_hash("first", "same-id")


def test_content_hash() -> None:
    job = normalized_listing()
    job.raw_payload = {"alpha": 1, "nested": {"a": 1, "b": 2}}
    original = job_content_hash(job)
    job.raw_payload = {"nested": {"b": 2, "a": 1}, "alpha": 1}
    assert job_content_hash(job) == original
    job.raw_payload["alpha"] = 2
    assert job_content_hash(job) != original
