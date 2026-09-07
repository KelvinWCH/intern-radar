from dataclasses import replace
from datetime import date
from typing import Literal

from pydantic import JsonValue

from job_backend.common.text_matching import matches_text
from job_backend.jobs.company_priority import company_tier
from job_backend.jobs.models import JobListItem, JobOverview, JobPage, JobUserData
from job_backend.matching.views import match_views
from job_backend.persistence.models import Document, Filter, Junction, Order, ReadQuery
from job_backend.persistence.session import Session

Sort = Literal[
    "recent", "posted", "prestige", "engineering", "match", "company", "title", "location"
]

GROUP_FIELD = "deduplication_key"
_LEAD = (Order("@status", ranks=(("new", 3),)),)
_INTERNAL_FIELDS = ("deduplication_key", "job_url_hash")


def job_scope(*, deleted: bool, eligible: bool) -> Junction:
    filters: list[Filter | Junction] = [Filter("deleted_at", "ne" if deleted else "eq")]
    if eligible:
        filters.extend(
            (
                Filter("is_visible", "ne", False),
                Junction(
                    (
                        Filter("source_type", "in", ["user_added", "user_auto_add"]),
                        Junction(
                            (
                                Filter("is_canada_internship", value=True),
                                Filter("is_toronto_area", "ne"),
                            )
                        ),
                    ),
                    "or",
                ),
            )
        )
    return Junction(tuple(filters))


def _label_filter(session: Session, query: ReadQuery, field: str, text: str) -> Filter:
    matches: list[JsonValue] = [
        value for value in session.values(query, field) if matches_text(text, value)
    ]
    return Filter(field, "in", matches)


def _priority(session: Session, query: ReadQuery) -> tuple[Order, ...]:
    ranks = tuple(
        (name, {"tech": 0, "known": 1, None: 2}[company_tier(name)])
        for name in session.values(query, "company")
    )
    # false and unknown both count as outside the gta
    return (Order("@outside_gta", numeric=True), Order("company", ranks=ranks))


def _copies(session: Session, rows: list[Document]) -> dict[str, int]:
    keys: list[JsonValue] = [
        *sorted({value for row in rows if isinstance(value := row.get(GROUP_FIELD), str)})
    ]
    if not keys:
        return {}
    query = ReadQuery("jobs", Junction((Filter("deleted_at"), Filter(GROUP_FIELD, "in", keys))))
    counts: dict[str, int] = {}
    for row in session.groups(query, (GROUP_FIELD,)):
        key, count = row.get(GROUP_FIELD), row.get("count")
        if isinstance(key, str) and isinstance(count, int):
            counts[key] = count
    return counts


def browse_jobs(
    session: Session,
    *,
    limit: int,
    offset: int,
    active: bool | None,
    toronto_area: bool | None,
    first_seen_from: int | None,
    first_seen_before: int | None,
    posted_from: date | None,
    posted_before: date | None,
    posted_timezone: str,
    q: str,
    company: str,
    location: str,
    source: str | None,
    application_status: str | None,
    tracked: bool,
    deleted: bool,
    flagged: bool | None,
    scope: str,
    sort: Sort | None,
    min_match: int | None = None,
) -> JobPage:
    filters: list[Filter | Junction] = [job_scope(deleted=deleted, eligible=scope == "eligible")]
    if active is not None:
        filters.append(Filter("active", "ne" if active else "eq", False))
    for field, value in (
        ("source", source or None),
        ("is_toronto_area", toronto_area),
        ("@status", application_status),
    ):
        if value is not None:
            filters.append(Filter(field, value=value))
    if tracked:
        filters.append(Filter("@status", "ne", "new"))
    if flagged is not None:
        filters.append(Filter("review_reason", "ne" if flagged else "eq"))
    if min_match is not None:
        filters.append(Filter("@match_score", "ge", min_match))
    for field, op, value in (
        ("first_seen_at", "ge", first_seen_from),
        ("first_seen_at", "lt", first_seen_before),
    ):
        if value is not None:
            filters.append(Filter(field, "ge" if op == "ge" else "lt", value))
    if posted_from is not None:
        filters.append(Filter("@day", "ge", posted_from.isoformat()))
    if posted_before is not None:
        filters.append(Filter("@day", "lt", posted_before.isoformat()))
    query = ReadQuery("jobs", Junction(tuple(filters)), timezone=posted_timezone)
    for field, text in (("company", company), ("@location", location)):
        if text.strip():
            filters.append(_label_filter(session, query, field, text))
    if q.strip():
        filters.append(
            Junction(
                (_label_filter(session, query, "@labels", q), Filter("@body", "contains", q)), "or"
            )
        )
    query = replace(query, where=Junction(tuple(filters)))
    recency = (Order("first_seen_at", descending=True, numeric=True), Order("@key"))
    if sort is None:
        field = (
            "first_seen_at"
            if first_seen_from is not None or first_seen_before is not None
            else "date_posted"
        )
        order = (Order(field, descending=True, numeric=True), Order("@key", descending=True))
    elif sort in {"prestige", "engineering"}:
        order = (
            ((Order("@engineering", numeric=True),) if sort == "engineering" else ())
            + _priority(session, query)
            + recency
        )
    elif sort == "match":
        order = (
            Order("@match_score", descending=True, numeric=True),
            *_priority(session, query),
            *recency,
        )
    elif sort == "posted":
        order = (Order("date_posted", descending=True, numeric=True), *recency)
    elif sort in {"company", "title", "location"}:
        order = (Order("@location" if sort == "location" else sort), *recency)
    else:
        order = recency
    page = session.select(
        replace(query, order=order, distinct=GROUP_FIELD, lead=_LEAD), limit=limit, offset=offset
    )
    ids = [item["id"] for item in page.items]
    users = (
        session.select(
            ReadQuery("job_user_data", Filter("job_id", "in", ids)), limit=limit, count=False
        ).items
        if ids
        else []
    )
    by_id = {row["job_id"]: row for row in users if isinstance(row["job_id"], str)}
    matches = match_views(session, [str(identity) for identity in ids])
    copies = _copies(session, page.items)
    items: list[JobListItem] = []
    for row in page.items:
        user: Document = dict(by_id.get(str(row["id"]), {}))
        user.pop("job_id", None)
        facts = {name: value for name, value in row.items() if name not in _INTERNAL_FIELDS}
        item = JobListItem.model_validate({**facts, "user": JobUserData.model_validate(user)})
        item.match = matches.get(item.id)
        key = row.get(GROUP_FIELD)
        item.copies = copies.get(key, 1) if isinstance(key, str) else 1
        items.append(item)
    return JobPage(items=items, total=page.total or 0, limit=limit, offset=offset)


def job_overview(session: Session, *, deleted: bool, eligible: bool) -> JobOverview:
    query = ReadQuery("jobs", job_scope(deleted=deleted, eligible=eligible), distinct=GROUP_FIELD)
    statuses: dict[str, int] = {}
    for row in session.groups(query, ("@status",)):
        status, count = row["@status"], row["count"]
        if not isinstance(status, str) or not isinstance(count, int):
            raise ValueError("Invalid job aggregate")
        statuses[status] = statuses.get(status, 0) + count
    sources = sorted(session.values(replace(query, distinct=None), "source"))
    return JobOverview(total=sum(statuses.values()), statuses=statuses, sources=sources)
