import hashlib
import json
import time
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import JsonValue

from job_backend.common.text_matching import contains_text
from job_backend.jobs.calendar_dates import posting_day
from job_backend.jobs.title_priority import engineering_title_priority
from job_backend.persistence.models import (
    Document,
    DocumentKey,
    Filter,
    Junction,
    Order,
    ReadPage,
    ReadQuery,
)
from job_backend.persistence.projections import project_record


def value(
    data: Document,
    key: str,
    field: str,
    query: ReadQuery,
    documents: Mapping[DocumentKey, Document],
) -> JsonValue:
    if field == "@elapsed":
        started, finished = data.get("started_at"), data.get("finished_at")
        return (
            max(0, int((finished or time.time()) - started))
            if isinstance(started, int | float)
            and (finished is None or isinstance(finished, int | float))
            else 0
        )
    if field == "@revision":
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    if field == "@key":
        return key
    if field == "@status":
        return documents.get(("job_user_data", key), {}).get("status", "new")
    if field == "@match_score":
        return documents.get(("job_matches", key), {}).get("score")
    if field == "@location":
        locations = data.get("locations", [])
        return " ".join(str(item) for item in locations) if isinstance(locations, list) else ""
    if field == "@labels":
        return " ".join(
            (
                str(data.get("title", "")),
                str(data.get("company", "")),
                str(value(data, key, "@location", query, documents)),
            )
        )
    if field == "@engineering":
        return engineering_title_priority(str(data.get("title", "")))
    if field == "@outside_gta":
        return 0 if data.get("is_toronto_area") is True else 1
    if field in {"@day", "@event_day"}:
        timestamp = data.get("date_posted" if field == "@day" else "occurred_at")
        zone = ZoneInfo(query.timezone)
        if isinstance(timestamp, int | float) and field == "@day":
            return posting_day(int(timestamp), zone).isoformat()
        if field == "@day":
            timestamp = data.get("first_seen_at")
        if not isinstance(timestamp, int | float):
            return None
        return datetime.fromtimestamp(timestamp, zone).date().isoformat()
    if field == "@body":
        return data.get("raw_description") or ""
    current: JsonValue = data
    for part in field.split("."):
        current = current.get(part) if isinstance(current, dict) else None
    return current


def matches(
    data: Document,
    key: str,
    predicate: Filter | Junction,
    query: ReadQuery,
    documents: Mapping[DocumentKey, Document],
) -> bool:
    if isinstance(predicate, Junction):
        results = (matches(data, key, child, query, documents) for child in predicate.children)
        return all(results) if predicate.mode == "and" else any(results)
    actual, expected = value(data, key, predicate.field, query, documents), predicate.value
    if predicate.op == "eq":
        return actual == expected
    if predicate.op == "ne":
        return actual != expected
    if predicate.op == "in":
        return isinstance(expected, list) and actual in expected
    if predicate.op == "contains":
        return contains_text(str(expected), str(actual or ""))
    if isinstance(actual, bool) or isinstance(expected, bool):
        return False
    if isinstance(actual, str) and isinstance(expected, str):
        left, right = (0, 1) if actual < expected else (1, 0) if actual > expected else (0, 0)
    elif isinstance(actual, int | float) and isinstance(expected, int | float):
        left, right = actual, expected
    else:
        return False
    return {"ge": left >= right, "gt": left > right, "lt": left < right, "le": left <= right}[
        predicate.op
    ]


def rows(documents: Mapping[DocumentKey, Document], query: ReadQuery) -> list[tuple[str, Document]]:
    return [
        (key, data)
        for (collection, key), data in documents.items()
        if collection == query.collection and matches(data, key, query.where, query, documents)
    ]


def _ordered(
    selected: list[tuple[str, Document]],
    orders: tuple[Order, ...],
    query: ReadQuery,
    documents: Mapping[DocumentKey, Document],
) -> list[tuple[str, Document]]:
    selected = sorted(selected, key=lambda row: row[0])
    for order in reversed(orders):

        def sort_value(row: tuple[str, Document], order: Order = order) -> str | int | float:
            found = value(row[1], row[0], order.field, query, documents)
            if found is None:
                return 0 if order.numeric or order.ranks else ""
            if order.ranks:
                return dict(order.ranks).get(str(found), 2)
            if isinstance(found, int | float):
                return found
            return str(found).casefold() if order.field != "@key" else str(found)

        selected.sort(key=sort_value, reverse=order.descending)
        selected.sort(key=lambda row: value(row[1], row[0], order.field, query, documents) is None)
    return selected


def _grouped(
    selected: list[tuple[str, Document]],
    query: ReadQuery,
    documents: Mapping[DocumentKey, Document],
) -> list[tuple[str, Document]]:
    if query.distinct is None:
        return selected
    kept: list[tuple[str, Document]] = []
    seen: set[str] = set()
    for key, data in _ordered(selected, (*query.lead, *query.order), query, documents):
        group = value(data, key, query.distinct, query, documents)
        label = key if group is None else str(group)
        if label not in seen:
            seen.add(label)
            kept.append((key, data))
    return kept


def select(
    documents: Mapping[DocumentKey, Document],
    query: ReadQuery,
    *,
    limit: int,
    offset: int,
    count: bool,
) -> ReadPage:
    if not 1 <= limit <= 1000 or offset < 0 or (query.source and not query.fields):
        raise ValueError("Invalid projected page")
    selected = _ordered(
        _grouped(rows(documents, query), query, documents), query.order, query, documents
    )
    page: list[Document] = []
    for key, data in selected[offset : offset + limit]:
        projected = (
            project_record(query.collection, data)
            if query.fields is None
            else {field: value(data, key, field, query, documents) for field in query.fields}
        )
        page.append(deepcopy(projected))
    return ReadPage(page, len(selected) if count else None)


def groups(
    documents: Mapping[DocumentKey, Document],
    query: ReadQuery,
    fields: tuple[str, ...],
    sums: tuple[str, ...],
) -> list[Document]:
    result: dict[str, Document] = {}
    members: dict[str, set[str]] = {}
    if not fields:
        result["[]"] = {"count": 0, **dict.fromkeys(sums)}
    for key, data in rows(documents, query):
        values = [value(data, key, field, query, documents) for field in fields]
        group = result.setdefault(
            repr(values),
            {**dict(zip(fields, values, strict=True)), "count": 0, **dict.fromkeys(sums)},
        )
        if query.distinct is not None:
            distinct = value(data, key, query.distinct, query, documents)
            members.setdefault(repr(values), set()).add(key if distinct is None else str(distinct))
            group["count"] = len(members[repr(values)])
        else:
            count = group["count"]
            assert isinstance(count, int)
            group["count"] = count + 1
        for field in sums:
            number = value(data, key, field, query, documents)
            if isinstance(number, int | float) and not isinstance(number, bool):
                previous = group[field]
                group[field] = (previous if isinstance(previous, int | float) else 0) + number
    return list(result.values())
