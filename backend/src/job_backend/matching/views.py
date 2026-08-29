from pydantic import JsonValue, TypeAdapter, ValidationError

from job_backend.matching.models import JobMatchView
from job_backend.persistence.models import Filter, ReadQuery
from job_backend.persistence.session import Session

_FIELDS = ("job_id", "score", "band", "reasons", "skills", "role", "components", "scored_at")
_VIEW = TypeAdapter(JobMatchView)


def match_views(session: Session, job_ids: list[str]) -> dict[str, JobMatchView]:
    if not job_ids:
        return {}
    members: list[JsonValue] = list(dict.fromkeys(job_ids))
    query = ReadQuery("job_matches", Filter("job_id", "in", members), fields=_FIELDS, source=True)
    views: dict[str, JobMatchView] = {}
    for row in session.select(query, limit=max(1, len(members)), count=False).items:
        identity = row.pop("job_id", None)
        if not isinstance(identity, str):
            continue
        try:
            views[identity] = _VIEW.validate_python(row, strict=False)
        except ValidationError:
            continue
    return views
