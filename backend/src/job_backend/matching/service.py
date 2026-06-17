import hashlib
import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import JsonValue

from job_backend.common.logger import get_logger
from job_backend.jobs.models import Job
from job_backend.matching.constants import (
    EMBED_BATCH,
    EMBED_SECONDS_PER_PASS,
    EMBEDDING_VERSION,
    MIN_DESCRIPTION_CHARS,
    SCORING_VERSION,
)
from job_backend.matching.embedding import Embedder, decode_vector, encode_vector
from job_backend.matching.models import JobEmbedding, JobMatch, MatchState, MatchStatus
from job_backend.matching.onnx_model import DIMENSIONS, MODEL_KEY
from job_backend.matching.scoring import (
    JobFacts,
    ProfileVectors,
    Similarities,
    calibrate,
    calibration_points,
    centroid,
    degree_gap,
    score_job,
    similarities,
)
from job_backend.matching.skills import SkillMatcher, inverse_frequencies
from job_backend.matching.texts import (
    background_query,
    graduation_years,
    job_description,
    job_passage,
    profile_degrees,
    profile_skills,
    role_queries,
    search_text,
)
from job_backend.persistence.database import Database
from job_backend.persistence.models import Document, Filter, Junction, ReadQuery
from job_backend.persistence.session import Session
from job_backend.profile.models import UserProfile
from job_backend.profile.service import read_user_profile

logger = get_logger(__name__)

EMBEDDING_KEY = f"{MODEL_KEY};passage+title;v{EMBEDDING_VERSION}"

POSITIVE_STATUSES = frozenset({"saved", "applied", "interviewing", "offered", "rejected"})
_PAGE = 1000
_WRITE_BATCH = 500
RECALIBRATE_GROWTH = 1.25
_SCORING_FIELDS = (
    "state_key",
    "model",
    "profile_revision",
    "positives",
    "negatives",
    "role_queries",
    "role_vectors",
    "background_vector",
    "positive_vector",
    "negative_vector",
    "calibration",
    "skill_idf",
    "calibrated_jobs",
)


@dataclass
class MatchRun:
    embedded: int = 0
    scored: int = 0
    pending: int = 0
    full: bool = False
    device: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class _Embedded:
    vector: NDArray[np.float32]
    title_vector: NDArray[np.float32]
    text: str
    graduation_years: list[int]
    described: bool


def _pages(session: Session, query: ReadQuery) -> Iterator[Document]:
    offset = 0
    while True:
        rows = session.select(query, limit=_PAGE, offset=offset, count=False).items
        yield from rows
        if len(rows) < _PAGE:
            return
        offset += _PAGE


def _string(value: JsonValue) -> str:
    return value if isinstance(value, str) else ""


def _flag(value: JsonValue) -> bool | None:
    return value if isinstance(value, bool) else None


def saved_jobs(session: Session) -> list[Document]:
    query = ReadQuery(
        "jobs",
        Filter("deleted_at"),
        fields=(
            "id",
            "content_hash",
            "title",
            "locations",
            "is_canada_internship",
            "is_toronto_area",
        ),
    )
    return list(_pages(session, query))


def feedback_ids(session: Session) -> tuple[list[str], list[str]]:
    positives: set[str] = set()
    for row in _pages(session, ReadQuery("job_user_data", fields=("job_id", "status"))):
        if row.get("status") in POSITIVE_STATUSES:
            positives.add(_string(row.get("job_id")))
    for row in _pages(session, ReadQuery("job_documents", fields=("job_id",))):
        positives.add(_string(row.get("job_id")))
    added = ReadQuery(
        "jobs",
        Junction(
            (Filter("deleted_at"), Filter("source_type", "in", ["user_added", "user_auto_add"]))
        ),
        fields=("id",),
    )
    positives.update(_string(row.get("id")) for row in _pages(session, added))
    deleted = ReadQuery("jobs", Filter("deleted_at", "ne"), fields=("id",))
    negatives = {_string(row.get("id")) for row in _pages(session, deleted)}
    positives -= negatives
    positives.discard("")
    negatives.discard("")
    return sorted(positives), sorted(negatives)


def state_key(revision: int, positives: list[str], negatives: list[str]) -> str:
    payload = json.dumps([SCORING_VERSION, EMBEDDING_KEY, revision, positives, negatives])
    return hashlib.sha256(payload.encode()).hexdigest()


def _records(session: Session, collection: str, fields: tuple[str, ...]) -> dict[str, Document]:
    query = ReadQuery(collection, fields=fields, source=True)
    return {_string(row.get("job_id")): row for row in _pages(session, query)}


def _stack(vectors: list[NDArray[np.float32]]) -> NDArray[np.float32]:
    if not vectors:
        return np.zeros((0, DIMENSIONS), dtype=np.float32)
    return np.asarray(vectors, dtype=np.float32)


class MatchService:
    def __init__(
        self,
        engine: Database,
        embedder_factory: Callable[[], Embedder],
        *,
        budget_seconds: float = EMBED_SECONDS_PER_PASS,
        clock: Callable[[], float] = time.monotonic,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> None:
        self.engine = engine
        self.embedder_factory = embedder_factory
        self.budget_seconds = budget_seconds
        self.clock = clock
        self.should_stop = should_stop
        self._embedder: Embedder | None = None

    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = self.embedder_factory()
        return self._embedder

    def refresh(self) -> MatchRun:
        run = MatchRun()
        saved = read_user_profile(self.engine)
        with Session(self.engine, read_only=True) as session:
            jobs = saved_jobs(session)
            positives, negatives = feedback_ids(session)
            embeddings = _records(session, "job_embeddings", ("job_id", "model", "content_hash"))
            matches = _records(session, "job_matches", ("job_id", "content_hash"))
            state = session.get(MatchState, "current", hydrate=False)
        if saved.profile is None:
            self._save_state(
                job_ids={_string(job.get("id")) for job in jobs},
                error="Save your profile to score jobs.",
            )
            run.note = "no profile"
            return run
        hashes = {_string(job.get("id")): _string(job.get("content_hash")) for job in jobs}
        # deleted jobs are only negative examples, never scored
        wanted = set(hashes) | set(negatives)
        stale = [
            identity
            for identity in sorted(wanted)
            if (record := embeddings.get(identity)) is None
            or record.get("model") != EMBEDDING_KEY
            or (identity in hashes and record.get("content_hash") != hashes[identity])
        ]
        priority = {_string(job.get("id")) for job in jobs if job.get("is_canada_internship")}
        stale.sort(key=lambda identity: identity not in priority)
        run.embedded = self._embed(stale)
        run.device = self._embedder.device if self._embedder is not None else None
        run.pending = len(stale) - run.embedded
        if run.pending:
            self._save_state(
                job_ids=set(hashes), embedded=len(wanted) - run.pending, device=run.device
            )
            return run
        key = state_key(saved.revision, positives, negatives)
        if (
            state is None
            or state.state_key != key
            or state.model != EMBEDDING_KEY
            or not state.calibration
            or len(jobs) > RECALIBRATE_GROWTH * max(1, state.calibrated_jobs)
        ):
            run.full = True
            run.scored = self._score_all(
                saved.profile, saved.revision, key, jobs, positives, negatives
            )
            run.device = self._embedder.device if self._embedder is not None else run.device
        else:
            due = {
                identity
                for identity, content in hashes.items()
                if (match := matches.get(identity)) is None or match.get("content_hash") != content
            }
            run.scored = self._score(
                saved.profile, state, [job for job in jobs if _string(job.get("id")) in due]
            )
            if (
                run.scored
                or run.embedded
                or (state.total, state.embedded)
                != (
                    len(jobs),
                    len(wanted),
                )
            ):
                self._save_state(job_ids=set(hashes), embedded=len(wanted), device=run.device)
        return run

    def _embed(self, stale: list[str]) -> int:
        deadline = self.clock() + self.budget_seconds
        done = 0
        for start in range(0, len(stale), EMBED_BATCH):
            if self.should_stop() or (done and self.clock() > deadline):
                break
            batch = stale[start : start + EMBED_BATCH]
            with Session(self.engine) as session:
                session.prefetch(Job, set(batch))
                jobs = [
                    job for identity in batch if (job := session.get(Job, identity, hydrate=False))
                ]
            descriptions = [job_description(job) for job in jobs]
            try:
                embedder = self.embedder()
                vectors = embedder.embed(
                    [job_passage(job, text) for job, text in zip(jobs, descriptions, strict=True)],
                    query=False,
                )
                titles = embedder.embed([job.title or job.company for job in jobs], query=False)
            except Exception:
                self._embedder = None
                raise
            now = int(time.time())
            with Session(self.engine) as session, session.begin():
                session.prefetch(JobEmbedding, {job.id for job in jobs})
                for job, description, vector, title in zip(
                    jobs, descriptions, vectors, titles, strict=True
                ):
                    record = session.get(JobEmbedding, job.id, hydrate=False)
                    if record is None:
                        record = JobEmbedding(job_id=job.id)
                        session.add(record)
                    record.model = EMBEDDING_KEY
                    record.content_hash = job.content_hash
                    record.vector = encode_vector(vector)
                    record.title_vector = encode_vector(title)
                    record.described = len(description) >= MIN_DESCRIPTION_CHARS
                    record.text = search_text(job, description)
                    record.graduation_years = graduation_years(job)
                    record.embedded_at = now
            done += len(batch)
        return done

    def _embedded(self, ids: set[str]) -> dict[str, _Embedded]:
        found: dict[str, _Embedded] = {}
        with Session(self.engine, read_only=True) as session:
            query = ReadQuery(
                "job_embeddings",
                fields=(
                    "job_id",
                    "model",
                    "vector",
                    "title_vector",
                    "text",
                    "graduation_years",
                    "described",
                ),
                source=True,
            )
            for row in _pages(session, query):
                identity = _string(row.get("job_id"))
                if identity not in ids or row.get("model") != EMBEDDING_KEY:
                    continue
                years = row.get("graduation_years")
                found[identity] = _Embedded(
                    vector=decode_vector(_string(row.get("vector"))),
                    title_vector=decode_vector(_string(row.get("title_vector"))),
                    text=_string(row.get("text")),
                    graduation_years=[year for year in years if isinstance(year, int)]
                    if isinstance(years, list)
                    else [],
                    described=row.get("described") is not False,
                )
        return found

    @staticmethod
    def _facts(
        jobs: list[Document],
        embedded: dict[str, _Embedded],
        matcher: SkillMatcher,
        degrees: list[str],
    ) -> list[JobFacts]:
        facts: list[JobFacts] = []
        for job in jobs:
            identity = _string(job.get("id"))
            stored = embedded.get(identity)
            if stored is None:
                continue
            locations = job.get("locations")
            facts.append(
                JobFacts(
                    job_id=identity,
                    content_hash=_string(job.get("content_hash")),
                    title=_string(job.get("title")),
                    locations=[item for item in locations if isinstance(item, str)]
                    if isinstance(locations, list)
                    else [],
                    is_canada_internship=_flag(job.get("is_canada_internship")),
                    is_toronto_area=_flag(job.get("is_toronto_area")),
                    graduation_years=stored.graduation_years,
                    skills=matcher.find(stored.text),
                    described=stored.described,
                    degree_gap=degree_gap(_string(job.get("title")), degrees),
                )
            )
        return facts

    def _score_all(
        self,
        profile: UserProfile,
        revision: int,
        key: str,
        jobs: list[Document],
        positives: list[str],
        negatives: list[str],
    ) -> int:
        roles = role_queries(profile)
        embedder = self.embedder()
        role_vectors = embedder.embed(roles, query=True)
        background = embedder.embed([background_query(profile)], query=True)[0]
        ids = {_string(job.get("id")) for job in jobs}
        embedded = self._embedded(ids | set(positives) | set(negatives))
        positive = centroid(_stack([embedded[i].vector for i in positives if i in embedded]))
        negative = centroid(_stack([embedded[i].vector for i in negatives if i in embedded]))
        profile_vectors = ProfileVectors(
            roles=role_vectors,
            role_labels=roles,
            background=background,
            positive=positive,
            negative=negative,
            positives=len(positives),
        )
        matcher = SkillMatcher(profile_skills(profile))
        facts = self._facts(jobs, embedded, matcher, profile_degrees(profile))
        counts = dict.fromkeys(matcher.skills, 0)
        for item in facts:
            for skill in item.skills:
                counts[skill] += 1
        raw = similarities(
            _stack([embedded[item.job_id].vector for item in facts]),
            _stack([embedded[item.job_id].title_vector for item in facts]),
            profile_vectors,
        )
        pool = [index for index, item in enumerate(facts) if item.is_canada_internship]
        calibration = calibration_points(raw, pool)
        state = MatchState(
            state_key=key,
            model=EMBEDDING_KEY,
            profile_revision=revision,
            positives=positives,
            negatives=negatives,
            role_queries=roles,
            role_vectors=[encode_vector(vector) for vector in role_vectors],
            background_vector=encode_vector(background),
            positive_vector=None if positive is None else encode_vector(positive),
            negative_vector=None if negative is None else encode_vector(negative),
            calibration=calibration,
            skill_idf=inverse_frequencies(counts, len(facts)),
            calibrated_jobs=len(facts),
        )
        written = self._write(profile, state, facts, raw)
        self._save_state(
            job_ids=ids,
            embedded=len(ids | set(negatives)),
            device=embedder.device,
            scoring=state,
        )
        return written

    def _score(self, profile: UserProfile, state: MatchState, jobs: list[Document]) -> int:
        if not jobs:
            return 0
        profile_vectors = ProfileVectors(
            roles=_stack([decode_vector(value) for value in state.role_vectors]),
            role_labels=state.role_queries,
            background=decode_vector(state.background_vector),
            positive=None
            if state.positive_vector is None
            else decode_vector(state.positive_vector),
            negative=None
            if state.negative_vector is None
            else decode_vector(state.negative_vector),
            positives=len(state.positives),
        )
        embedded = self._embedded({_string(job.get("id")) for job in jobs})
        facts = self._facts(
            jobs, embedded, SkillMatcher(profile_skills(profile)), profile_degrees(profile)
        )
        if not facts:
            return 0
        raw = similarities(
            _stack([embedded[item.job_id].vector for item in facts]),
            _stack([embedded[item.job_id].title_vector for item in facts]),
            profile_vectors,
        )
        return self._write(profile, state, facts, raw)

    def _write(
        self, profile: UserProfile, state: MatchState, facts: list[JobFacts], raw: Similarities
    ) -> int:
        role = calibrate(raw.role, state.calibration.get("role", []))
        background = calibrate(raw.background, state.calibration.get("background", []))
        feedback = (
            calibrate(raw.feedback, state.calibration.get("feedback", []))
            if raw.feedback is not None
            else None
        )
        preferences = profile.preferences
        now = int(time.time())
        changed = 0
        for start in range(0, len(facts), _WRITE_BATCH):
            chunk = facts[start : start + _WRITE_BATCH]
            with Session(self.engine) as session, session.begin():
                session.prefetch(JobMatch, {item.job_id for item in chunk})
                for offset, item in enumerate(chunk):
                    index = start + offset
                    result = score_job(
                        item,
                        role=float(role[index]),
                        role_label=state.role_queries[int(raw.role_index[index])]
                        if state.role_queries
                        else None,
                        background=float(background[index]),
                        feedback=None if feedback is None else float(feedback[index]),
                        positives=len(state.positives),
                        idf=state.skill_idf,
                        preferred_locations=preferences.preferred_locations,
                        graduation_year=preferences.graduation_year,
                    )
                    record = session.get(JobMatch, item.job_id, hydrate=False)
                    if record is None:
                        record = JobMatch(job_id=item.job_id)
                        session.add(record)
                    elif (
                        record.content_hash == item.content_hash
                        and record.score == result.score
                        and record.band == result.band
                        and record.reasons == result.reasons
                        and record.skills == result.skills
                        and record.role == result.role
                    ):
                        continue
                    record.content_hash = item.content_hash
                    record.score = result.score
                    record.band = result.band
                    record.reasons = result.reasons
                    record.skills = result.skills
                    record.role = result.role
                    record.components = result.components
                    record.scored_at = now
                    changed += 1
        return changed

    def _save_state(
        self,
        *,
        job_ids: set[str],
        embedded: int | None = None,
        device: str | None = None,
        error: str | None = None,
        scoring: MatchState | None = None,
    ) -> None:
        bands: dict[str, int] = {}
        with Session(self.engine, read_only=True) as session:
            for identity, row in _records(session, "job_matches", ("job_id", "band")).items():
                if identity in job_ids:
                    band = _string(row.get("band"))
                    bands[band] = bands.get(band, 0) + 1
        with Session(self.engine) as session, session.begin():
            current = session.get(MatchState, "current", hydrate=False)
            if current is None:
                current = MatchState()
                session.add(current)
            if scoring is not None:
                for name in _SCORING_FIELDS:
                    setattr(current, name, getattr(scoring, name))
            current.total = len(job_ids)
            if embedded is not None:
                current.embedded = embedded
            if device:
                current.device = device
            current.scored = sum(bands.values())
            current.bands = bands
            current.error = error
            current.updated_at = int(time.time())


def match_status(engine: Database) -> MatchStatus:
    with Session(engine, read_only=True) as session:
        state = session.get(MatchState, "current", hydrate=False)
    if state is None:
        return MatchStatus(
            model=None,
            device=None,
            total=0,
            embedded=0,
            scored=0,
            bands={},
            profile_revision=0,
            positives=0,
            negatives=0,
            updated_at=None,
            error=None,
        )
    return MatchStatus(
        model=state.model or None,
        device=state.device or None,
        total=state.total,
        embedded=state.embedded,
        scored=state.scored,
        bands=state.bands,
        profile_revision=state.profile_revision,
        positives=len(state.positives),
        negatives=len(state.negatives),
        updated_at=state.updated_at or None,
        error=state.error,
    )
