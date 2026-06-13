from pathlib import Path

from fastapi.testclient import TestClient

from job_backend.jobs.models import Job, JobPage, JobResponse, JobUserRecord
from job_backend.main import create_app
from job_backend.matching.models import JobEmbedding, JobMatch, MatchState, MatchStatus
from job_backend.matching.service import MatchService
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from tests.matching.helpers import FakeEmbedder, add_job, profile, save

MARKETING = (
    "Plan seasonal promotions, write newsletters, coordinate events, and report on "
    "campaign attendance for our retail stores. " * 6
)


def _service(engine: Database, embedder: FakeEmbedder) -> MatchService:
    return MatchService(engine, lambda: embedder)


def _match(engine: Database, identity: str) -> JobMatch:
    with Session(engine) as session:
        match = session.get(JobMatch, identity, hydrate=False)
        assert match is not None
        return match


def _collection(engine: Database) -> None:
    save(engine, profile())
    add_job(engine, "job-swe", "Software Engineering Intern")
    add_job(
        engine,
        "job-marketing",
        "Marketing Coordinator",
        locations=["Calgary, AB, Canada"],
        description=MARKETING,
        canada_internship=False,
        toronto=False,
    )
    add_job(engine, "job-ml", "Machine Learning Intern", locations=["Markham, ON, Canada"])


def test_first_run_scores_all(engine: Database) -> None:
    _collection(engine)
    embedder = FakeEmbedder()
    run = _service(engine, embedder).refresh()
    assert (run.embedded, run.scored, run.pending, run.full) == (3, 3, 0, True)
    swe, marketing = _match(engine, "job-swe"), _match(engine, "job-marketing")
    assert swe.score > marketing.score
    assert swe.band in {"strong", "good"} and marketing.band == "low"
    assert "Uses Python, Redis, TypeScript" in swe.reasons
    assert "In Toronto" in swe.reasons
    assert "Not a student role" in marketing.reasons
    with Session(engine) as session:
        embedding = session.get(JobEmbedding, "job-ml", hydrate=False)
        state = session.get(MatchState, "current", hydrate=False)
        assert embedding is not None and embedding.described
        assert embedding.text.startswith("Machine Learning Intern")
        assert state is not None and state.scored == 3 and state.device == "test"
        assert state.bands.get("low") == 1


def test_unchanged_collection_does_no_work(engine: Database) -> None:
    _collection(engine)
    embedder = FakeEmbedder()
    service = _service(engine, embedder)
    service.refresh()
    calls = embedder.calls
    run = service.refresh()
    assert (run.embedded, run.scored, run.full) == (0, 0, False)
    assert embedder.calls == calls


def test_profile_change_rescores(engine: Database) -> None:
    _collection(engine)
    service = _service(engine, FakeEmbedder())
    service.refresh()
    save(engine, profile(preferred_locations=["Markham, ON"]), revision=1)
    run = service.refresh()
    assert run.full and run.embedded == 0
    assert "In Markham" in _match(engine, "job-ml").reasons
    with Session(engine) as session, session.begin():
        session.add(JobUserRecord(job_id="job-ml", status="saved"))
    assert service.refresh().full
    with Session(engine) as session:
        state = session.get(MatchState, "current", hydrate=False)
        assert state is not None and state.positives == ["job-ml"]
        assert state.positive_vector is not None


def test_deleted_jobs_not_scored(engine: Database) -> None:
    _collection(engine)
    with Session(engine) as session, session.begin():
        job = session.get(Job, "job-marketing", hydrate=False)
        assert job is not None
        job.deleted_at = 1
    _service(engine, FakeEmbedder()).refresh()
    with Session(engine) as session:
        state = session.get(MatchState, "current", hydrate=False)
        assert state is not None
        assert state.negatives == ["job-marketing"] and state.negative_vector is not None
        assert session.get(JobMatch, "job-marketing", hydrate=False) is None
        assert session.get(JobEmbedding, "job-marketing", hydrate=False) is not None


def test_match_api(engine: Database) -> None:
    assert engine.local_path is not None
    _collection(engine)
    _service(engine, FakeEmbedder()).refresh()
    with TestClient(create_app(Path(engine.local_path))) as client:
        page = JobPage.model_validate_json(
            client.get("/jobs", params={"scope": "all", "sort": "match"}).content
        )
        scores = [item.match.score for item in page.items if item.match is not None]
        assert len(scores) == 3 and scores == sorted(scores, reverse=True)
        strong_only = JobPage.model_validate_json(
            client.get(
                "/jobs", params={"scope": "all", "sort": "match", "min_match": scores[0]}
            ).content
        )
        assert [item.id for item in strong_only.items] == [page.items[0].id]
        detail = JobResponse.model_validate_json(client.get("/jobs/job-swe").content)
        assert detail.match is not None and detail.match.reasons
        status = MatchStatus.model_validate_json(client.get("/matches/status").content)
        assert (status.total, status.embedded, status.scored) == (3, 3, 3)
        assert client.get("/jobs", params={"min_match": 101}).status_code == 422
