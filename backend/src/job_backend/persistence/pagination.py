import base64
import binascii
import hashlib
import json
from typing import TypeVar

from pydantic import Field, JsonValue, ValidationError

from job_backend.common.models import StrictModel
from job_backend.persistence.models import (
    Document,
    Filter,
    Junction,
    Order,
    ReadQuery,
    StoredRecord,
)
from job_backend.persistence.session import Session

Record = TypeVar("Record", bound=StoredRecord)


class HistoryCursor(StrictModel):
    scope: str
    timestamp: int | float = Field(ge=0, allow_inf_nan=False)
    identity: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,200}$")
    offset: int = Field(ge=0)


def history_page(
    session: Session,
    model: type[Record],
    field: str,
    *,
    limit: int,
    offset: int,
    cursor: str,
    equal: dict[str, JsonValue],
) -> tuple[list[Record], str | None]:
    if not 1 <= limit <= 100:
        raise ValueError("Choose a page size between 1 and 100")
    scope = hashlib.sha256(
        json.dumps([model.collection, field, equal, limit], sort_keys=True).encode()
    ).hexdigest()
    after: tuple[int | float, str] | None = None
    if cursor:
        try:
            decoded = HistoryCursor.model_validate_json(base64.urlsafe_b64decode(cursor))
        except (ValueError, ValidationError, binascii.Error):
            raise ValueError("Invalid page cursor; return to the first page") from None
        if decoded.scope != scope or decoded.offset != offset:
            raise ValueError("Page cursor does not match these filters; return to the first page")
        after = decoded.timestamp, decoded.identity
    elif offset:
        raise ValueError("A continuation cursor is required after the first page")
    rows = session.window(model, field, limit=limit + 1, after=after)
    selected = rows[:limit]
    following = None
    if len(rows) > limit:
        last = selected[-1]
        timestamp = last.to_document()[field]
        if not isinstance(timestamp, int | float) or isinstance(timestamp, bool):
            raise ValueError("History timestamp must be numeric")
        following = base64.urlsafe_b64encode(
            HistoryCursor(
                scope=scope,
                timestamp=timestamp,
                identity=str(last.identity()[0]),
                offset=offset + limit,
            )
            .model_dump_json()
            .encode()
        ).decode()
    return [
        row for row in selected if all(row.to_document().get(k) == v for k, v in equal.items())
    ], following


def projected_history_page(
    session: Session,
    model: type[StoredRecord],
    field: str,
    *,
    limit: int,
    offset: int,
    cursor: str,
    equal: dict[str, JsonValue],
    source_fields: tuple[str, ...] | None = None,
) -> tuple[list[Document], str | None]:
    if not 1 <= limit <= 100:
        raise ValueError("Choose a page size between 1 and 100")
    scope = hashlib.sha256(
        json.dumps([model.collection, field, equal, limit], sort_keys=True).encode()
    ).hexdigest()
    where: Filter | Junction = Filter(field, "ne")
    if cursor:
        try:
            decoded = HistoryCursor.model_validate_json(base64.urlsafe_b64decode(cursor))
        except (ValueError, ValidationError, binascii.Error):
            raise ValueError("Invalid page cursor; return to the first page") from None
        if decoded.scope != scope or decoded.offset != offset:
            raise ValueError("Page cursor does not match these filters; return to the first page")
        where = Junction(
            (
                where,
                Junction(
                    (
                        Filter(field, "lt", decoded.timestamp),
                        Junction(
                            (
                                Filter(field, value=decoded.timestamp),
                                Filter("@key", "lt", decoded.identity),
                            )
                        ),
                    ),
                    "or",
                ),
            )
        )
    elif offset:
        raise ValueError("A continuation cursor is required after the first page")
    rows = session.select(
        ReadQuery(
            model.collection,
            where,
            (Order(field, descending=True, numeric=True), Order("@key", descending=True)),
            fields=source_fields,
            source=source_fields is not None,
        ),
        limit=limit + 1,
        count=False,
    ).items
    selected = rows[:limit]
    following = None
    if len(rows) > limit:
        timestamp, identity = selected[-1][field], selected[-1]["id"]
        if (
            not isinstance(timestamp, int | float)
            or isinstance(timestamp, bool)
            or not isinstance(identity, str)
        ):
            raise ValueError("Invalid history boundary")
        following = base64.urlsafe_b64encode(
            HistoryCursor(
                scope=scope, timestamp=timestamp, identity=identity, offset=offset + limit
            )
            .model_dump_json()
            .encode()
        ).decode()
    return [
        row for row in selected if all(row.get(key) == value for key, value in equal.items())
    ], following
