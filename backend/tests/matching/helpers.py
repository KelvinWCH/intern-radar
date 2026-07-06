import hashlib
import re

import numpy as np
from numpy.typing import NDArray

from job_backend.jobs.models import Job
from job_backend.matching.onnx_model import DIMENSIONS, MODEL_KEY
from job_backend.persistence.database import Database
from job_backend.persistence.session import Session
from job_backend.profile.models import CandidatePreferences, UserProfile
from job_backend.resumes.storage import save_profile
from tests.resumes.helpers import candidate_profile


class FakeEmbedder:
    model = MODEL_KEY

    def __init__(self) -> None:
        self.device = "test"
        self.calls = 0
        self.texts: list[str] = []

    def embed(self, texts: list[str], *, query: bool) -> NDArray[np.float32]:
        self.calls += 1
        self.texts.extend(texts)
        vectors = np.zeros((len(texts), DIMENSIONS), dtype=np.float32)
        for row, text in enumerate(texts):
            vectors[row, 0] = 0.05
            for word in re.findall(r"[a-z]+", text.lower()):
                digest = int(hashlib.sha256(word.encode()).hexdigest(), 16)
                vectors[row, 1 + digest % (DIMENSIONS - 1)] += 1.0
        norms = np.sqrt(np.sum(vectors * vectors, axis=1, keepdims=True))
        return np.asarray(vectors / norms, dtype=np.float32)


def profile(**preferences: object) -> UserProfile:
    base = candidate_profile()
    choices = {
        "target_roles": ["Software Engineering Intern", "Machine Learning Intern"],
        "preferred_locations": ["Toronto, ON"],
        "graduation_year": 2028,
        **preferences,
    }
    return base.model_copy(update={"preferences": CandidatePreferences.model_validate(choices)})


def save(engine: Database, candidate: UserProfile, revision: int = 0) -> None:
    save_profile(engine, candidate, expected_revision=revision)


DESCRIPTION = (
    "You will build Python services and TypeScript dashboards with Redis caching. "
    "We look for students who enjoy software engineering and machine learning. " * 6
)


def add_job(
    engine: Database,
    identity: str,
    title: str,
    *,
    company: str = "Example",
    locations: list[str] | None = None,
    description: str = DESCRIPTION,
    canada_internship: bool = True,
    toronto: bool = True,
    content: str = "a",
) -> None:
    with Session(engine) as session, session.begin():
        existing = session.get(Job, identity, hydrate=False)
        job = existing or Job(id=identity)
        job.source = "example"
        job.external_id = identity
        job.title = title
        job.company = company
        job.locations = locations if locations is not None else ["Toronto, ON, Canada"]
        job.cleaned_description = description
        job.raw_description = description
        job.is_canada_internship = canada_internship
        job.is_toronto_area = toronto
        job.content_hash = hashlib.sha256(content.encode()).hexdigest()
        job.job_hash = "0" * 64
        if existing is None:
            session.add(job)
