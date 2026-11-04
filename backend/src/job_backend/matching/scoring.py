import math
import re
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from job_backend.common.text_matching import normalized_text
from job_backend.matching.constants import (
    BACKGROUND_WEIGHT,
    BANDS,
    CALIBRATION_POINTS,
    ELIGIBILITY_FACTOR,
    ELSEWHERE_IN_CANADA,
    FEEDBACK_FULL_AT,
    FEEDBACK_MAX_WEIGHT,
    FEEDBACK_REASON_AT,
    LOCATION_WEIGHT,
    MAX_REASON_SKILLS,
    MAX_STORED_SKILLS,
    MIN_CALIBRATION_POOL,
    NEGATIVE_FEEDBACK_WEIGHT,
    NON_STUDENT_FACTOR,
    OFF_ROLE_BELOW,
    OFF_ROLE_FACTOR,
    OUTSIDE_CANADA,
    PREFERRED_LOCATION,
    ROLE_WEIGHT,
    SKILL_SATURATION_IDFS,
    SKILLS_WEIGHT,
    TITLE_ROLE_SHARE,
    TORONTO_AREA,
    UNDESCRIBED_MAX_SCORE,
    UNKNOWN_LOCATION,
)
from job_backend.matching.models import MatchBand
from job_backend.scrape.pipeline.heuristics.classification import (
    classify_locations,
    internship_title,
)


@dataclass(frozen=True)
class ProfileVectors:
    roles: NDArray[np.float32]
    role_labels: list[str]
    background: NDArray[np.float32]
    positive: NDArray[np.float32] | None = None
    negative: NDArray[np.float32] | None = None
    positives: int = 0


@dataclass(frozen=True)
class JobFacts:
    job_id: str
    content_hash: str
    title: str
    locations: list[str]
    is_canada_internship: bool | None
    is_toronto_area: bool | None
    graduation_years: list[int] = field(default_factory=list[int])
    skills: set[str] = field(default_factory=set[str])
    described: bool = True
    degree_gap: str | None = None


@dataclass(frozen=True)
class Similarities:
    role: NDArray[np.float32]
    role_index: NDArray[np.int64]
    background: NDArray[np.float32]
    feedback: NDArray[np.float32] | None


@dataclass(frozen=True)
class ScoredJob:
    score: int
    band: MatchBand
    reasons: list[str]
    skills: list[str]
    role: str | None
    components: dict[str, float]


def centroid(vectors: NDArray[np.float32]) -> NDArray[np.float32] | None:
    if not len(vectors):
        return None
    mean = vectors.mean(axis=0)
    norm = float(np.sqrt(mean @ mean))
    return (mean / norm).astype(np.float32) if norm > 0 else None


def similarities(
    vectors: NDArray[np.float32], titles: NDArray[np.float32], profile: ProfileVectors
) -> Similarities:
    by_role = TITLE_ROLE_SHARE * (titles @ profile.roles.T) + (1 - TITLE_ROLE_SHARE) * (
        vectors @ profile.roles.T
    )
    feedback: NDArray[np.float32] | None = None
    if profile.positive is not None:
        liked = np.asarray(vectors @ profile.positive, dtype=np.float32)
        if profile.negative is not None:
            disliked = np.asarray(vectors @ profile.negative, dtype=np.float32)
            liked = np.asarray(liked - NEGATIVE_FEEDBACK_WEIGHT * disliked, dtype=np.float32)
        feedback = liked
    return Similarities(
        role=by_role.max(axis=1).astype(np.float32),
        role_index=by_role.argmax(axis=1).astype(np.int64),
        background=(vectors @ profile.background).astype(np.float32),
        feedback=None if feedback is None else feedback.astype(np.float32),
    )


def quantiles(values: NDArray[np.float32]) -> list[float]:
    if not len(values):
        return []
    ordered = np.asarray(sorted(float(value) for value in values), dtype=np.float64)
    positions = np.linspace(0.0, len(ordered) - 1.0, CALIBRATION_POINTS)
    points = np.interp(positions, np.arange(len(ordered), dtype=np.float64), ordered)
    return [round(float(point), 6) for point in points]


def calibration_points(raw: Similarities, pool: list[int]) -> dict[str, list[float]]:
    chosen = np.asarray(pool, dtype=np.int64) if len(pool) >= MIN_CALIBRATION_POOL else None

    def part(values: NDArray[np.float32]) -> list[float]:
        return quantiles(values if chosen is None else values[chosen])

    points = {"role": part(raw.role), "background": part(raw.background)}
    if raw.feedback is not None:
        points["feedback"] = part(raw.feedback)
    return points


def calibrate(values: NDArray[np.float32], points: list[float]) -> NDArray[np.float64]:
    if len(points) < 2:
        return np.full(len(values), 0.5)
    # points have to keep increasing or interp divides by zero
    grid: list[float] = []
    for index, point in enumerate(points):
        grid.append(max(point + index * 1e-9, grid[-1] + 1e-12) if grid else point)
    return np.interp(values, np.asarray(grid), np.linspace(0.0, 1.0, len(grid)))


def location_part(
    locations: list[str], is_toronto_area: bool | None, preferred: list[str]
) -> tuple[float, str | None]:
    folded = [normalized_text(location) for location in locations]
    for wanted in preferred:
        city = normalized_text(wanted.split(",")[0])
        pattern = re.compile(rf"\b{re.escape(city)}\b")
        if city and any(pattern.search(location) for location in folded):
            return PREFERRED_LOCATION, f"In {wanted.split(',')[0].strip()}"
    if is_toronto_area:
        return TORONTO_AREA, "Toronto area"
    if not locations:
        return UNKNOWN_LOCATION, None
    canada, _toronto = classify_locations(locations)
    if canada:
        return ELSEWHERE_IN_CANADA, "Elsewhere in Canada"
    remote = any("remote" in location for location in folded)
    return (UNKNOWN_LOCATION, None) if remote else (OUTSIDE_CANADA, "Outside Canada")


def skills_part(found: set[str], idf: dict[str, float]) -> tuple[float, list[str]]:
    ranked = sorted(found, key=lambda skill: (-idf.get(skill, 1.0), skill.casefold()))
    if not idf:
        return 0.0, ranked
    weights = sorted(idf.values())
    scale = SKILL_SATURATION_IDFS * weights[len(weights) // 2]
    total = sum(idf.get(skill, 1.0) for skill in found)
    return 1.0 - math.exp(-total / scale) if scale > 0 else 0.0, ranked


_DEGREE_TITLES = (
    ("PhD", re.compile(r"\bph\.?\s?d\b|\bdoctoral\b|\bdoctorate\b", re.IGNORECASE)),
    (
        "master's",
        re.compile(r"\bmaster'?s\b|\bmasters\b|\bm\.?sc\b|\bm\.?eng\b|\bmba\b", re.IGNORECASE),
    ),
)
_DEGREE_LEVELS = {
    "PhD": re.compile(r"\bph\.?\s?d\b|\bdoctor", re.IGNORECASE),
    "master's": re.compile(
        r"\bmaster|\bm\.?sc\b|\bm\.?eng\b|\bmba\b|\bph\.?\s?d\b|\bdoctor", re.IGNORECASE
    ),
}


def degree_gap(title: str, degrees: list[str]) -> str | None:
    for level, pattern in _DEGREE_TITLES:
        if pattern.search(title) and not any(_DEGREE_LEVELS[level].search(d) for d in degrees):
            return level
    return None


def band_for(score: int) -> MatchBand:
    for band, minimum in BANDS:
        if score >= minimum:
            return band
    return "low"


def score_job(
    facts: JobFacts,
    *,
    role: float,
    role_label: str | None,
    background: float,
    feedback: float | None,
    positives: int,
    idf: dict[str, float],
    preferred_locations: list[str],
    graduation_year: int | None,
) -> ScoredJob:
    skills, ranked = skills_part(facts.skills, idf)
    location, place = location_part(facts.locations, facts.is_toronto_area, preferred_locations)
    parts = [(ROLE_WEIGHT, role), (BACKGROUND_WEIGHT, background), (LOCATION_WEIGHT, location)]
    if facts.described:
        parts.append((SKILLS_WEIGHT, skills))
    base = sum(weight * value for weight, value in parts) / sum(weight for weight, _ in parts)
    weight = 0.0
    if feedback is not None and positives:
        weight = FEEDBACK_MAX_WEIGHT * min(1.0, positives / FEEDBACK_FULL_AT)
        base = (1 - weight) * base + weight * feedback
    student = 1.0 if facts.is_canada_internship or internship_title(facts.title) else 0.0
    year_gap = (
        graduation_year is not None
        and bool(facts.graduation_years)
        and graduation_year not in facts.graduation_years
    )
    eligible = 0.0 if year_gap or facts.degree_gap else 1.0
    off_role = role < OFF_ROLE_BELOW
    total = base * (1.0 if student else NON_STUDENT_FACTOR)
    total *= 1.0 if eligible else ELIGIBILITY_FACTOR
    total *= OFF_ROLE_FACTOR if off_role else 1.0
    score = max(0, min(100 if facts.described else UNDESCRIBED_MAX_SCORE, round(100 * total)))
    reasons: list[str] = []
    if role_label and role >= 0.85:
        reasons.append(f"Close to {role_label}")
    if ranked:
        reasons.append("Uses " + ", ".join(ranked[:MAX_REASON_SKILLS]))
    if feedback is not None and weight and feedback >= FEEDBACK_REASON_AT:
        reasons.append("Like jobs you saved or applied to")
    if place:
        reasons.append(place)
    if not facts.described:
        reasons.append("Scored from the title; little description was saved")
    if off_role:
        reasons.append("Far from your target roles")
    if not student:
        reasons.append("Not a student role")
    if facts.degree_gap:
        reasons.append(f"For {facts.degree_gap} students")
    if year_gap:
        years = ", ".join(str(year) for year in facts.graduation_years)
        reasons.append(f"Asks for graduation in {years}")
    components = {
        "role": round(role, 3),
        "background": round(background, 3),
        "location": round(location, 3),
        "student": student,
        "eligibility": eligible,
    }
    if facts.described:
        components["skills"] = round(skills, 3)
    if feedback is not None and weight:
        components["feedback"] = round(feedback, 3)
    return ScoredJob(
        score=score,
        band=band_for(score),
        reasons=reasons,
        skills=ranked[:MAX_STORED_SKILLS],
        role=role_label,
        components=components,
    )
