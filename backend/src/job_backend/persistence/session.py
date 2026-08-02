import json
from collections.abc import Callable, Generator
from contextlib import contextmanager
from types import TracebackType
from typing import TypeVar

from pydantic import JsonValue

from job_backend.persistence.database import Database
from job_backend.persistence.errors import ConflictError
from job_backend.persistence.identity import document_id
from job_backend.persistence.models import (
    Document,
    DocumentKey,
    Interval,
    OneOf,
    ReadPage,
    ReadQuery,
    StoredRecord,
    record_adapter,
)

Record = TypeVar("Record", bound=StoredRecord)


def _matches(data: Document, equal: dict[str, JsonValue], interval: Interval | None) -> bool:
    if interval is not None:
        field, start, end = interval
        value = data.get(field)
        if not (
            isinstance(value, int | float)
            and (start is None or value >= start)
            and (end is None or value < end)
        ):
            return False
    return all(data.get(field) == value for field, value in equal.items())


class Records(list[Record]):
    def first(self) -> Record | None:
        return self[0] if self else None

    def one(self) -> Record:
        if len(self) != 1:
            raise ValueError(f"Expected one record, got {len(self)}")
        return self[0]

    def all(self) -> list[Record]:
        return list(self)


class Session:
    def __init__(
        self,
        engine: Database,
        *,
        expire_on_commit: bool = False,
        read_only: bool = False,
    ) -> None:
        self.engine = engine
        self.read_only = read_only
        self.expected: dict[DocumentKey, Document | None] = {}
        self.records: dict[DocumentKey, StoredRecord] = {}
        self.deleted: set[DocumentKey] = set()
        self.hydrated: set[DocumentKey] = set()
        self.queries: dict[tuple[str, str], list[tuple[str, Document]]] = {}

    def __enter__(self) -> "Session":
        return self

    def __exit__(
        self,
        _kind: type[BaseException] | None,
        _error: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.rollback()

    @contextmanager
    def begin(self) -> Generator["Session"]:
        self._require_writable()
        try:
            yield self
            self.commit()
        except BaseException:
            self.rollback()
            raise

    def select(
        self, query: ReadQuery, *, limit: int, offset: int = 0, count: bool = True
    ) -> ReadPage:
        return self.engine.gateway.select(query, limit=limit, offset=offset, count=count)

    def groups(
        self, query: ReadQuery, fields: tuple[str, ...], sums: tuple[str, ...] = ()
    ) -> list[Document]:
        return self.engine.gateway.groups(query, fields, sums)

    def values(self, query: ReadQuery, field: str) -> list[str]:
        return self.engine.gateway.values(query, field)

    def get(
        self,
        model: type[Record],
        identity: str | int | tuple[str | int, ...],
        *,
        hydrate: bool = True,
    ) -> Record | None:
        key = (
            model.collection,
            document_id(identity if isinstance(identity, tuple) else (identity,)),
        )
        if key in self.deleted:
            return None
        existing = self.records.get(key)
        if existing is not None:
            if not isinstance(existing, model):
                raise TypeError("Document type mismatch")
            if hydrate:
                self._hydrate(key, existing)
            return existing
        if key in self.expected and self.expected[key] is None:
            return None

        data = self.engine.gateway.read(key)
        self.expected[key] = data
        if data is None:
            return None
        record = self._track(model, key, data)
        if hydrate:
            self._hydrate(key, record)
        return record

    def prefetch(self, model: type[Record], identities: set[str]) -> None:
        self._require_writable()
        keys = [
            (model.collection, document_id((identity,)))
            for identity in sorted(identities)
            if (model.collection, document_id((identity,))) not in self.expected
        ]
        if not keys:
            return
        snapshots = self.engine.gateway.read_many(keys)
        for key in keys:
            data = snapshots[key]
            self.expected[key] = data
            if data is not None:
                self._track(model, key, data)

    def _require_writable(self) -> None:
        if self.read_only:
            raise RuntimeError("Read-only sessions cannot write")

    def _track(self, model: type[Record], key: DocumentKey, data: Document) -> Record:
        existing = self.records.get(key)
        if isinstance(existing, model):
            return existing
        record = record_adapter(model).validate_python(data)
        if not isinstance(record, model):
            raise TypeError("Invalid stored record type")
        self.records[key] = record
        self.expected[key] = data
        return record

    def _hydrate(self, key: DocumentKey, record: StoredRecord) -> None:
        from job_backend.jobs.document_response import document_summaries
        from job_backend.jobs.models import Job, JobUserRecord

        if key in self.hydrated:
            return
        self.hydrated.add(key)
        if isinstance(record, Job):
            record.user = self.get(JobUserRecord, record.id)
        elif isinstance(record, JobUserRecord):
            record.documents = document_summaries(self, {record.job_id}).get(record.job_id, [])

    def all(self, model: type[Record], **equal: JsonValue) -> list[Record]:
        return self._all(model, equal)

    def _all(
        self,
        model: type[Record],
        equal: dict[str, JsonValue],
        interval: Interval | None = None,
    ) -> list[Record]:
        rows: dict[str, Record] = {}
        query = (model.collection, json.dumps([equal, interval], sort_keys=True))
        if query not in self.queries:
            self.queries[query] = self.engine.gateway.find(
                model.collection, equal, interval=interval
            )
        for identity, data in self.queries[query]:
            key = (model.collection, identity)
            if key not in self.deleted:
                rows[identity] = self._track(model, key, data)
        for key, record in list(self.records.items()):
            if isinstance(record, model) and key not in self.deleted:
                data = record.to_document()
                if _matches(data, equal, interval):
                    rows[key[1]] = record
                else:
                    rows.pop(key[1], None)
        return list(rows.values())

    def match_any(self, model: type[Record], field: str, values: set[str]) -> list[Record]:
        if not values:
            return []
        complete = model.collection, json.dumps([{}, None], sort_keys=True)
        if self.read_only and complete in self.queries:
            return [
                self._track(model, (model.collection, identity), data)
                for identity, data in self.queries[complete]
                if isinstance(value := data.get(field), str) and value in values
            ]
        candidates: dict[str, Record] = {}
        selected: list[JsonValue] = list(sorted(values))
        query = model.collection, json.dumps(["one_of", field, selected])
        if query not in self.queries:
            self.queries[query] = self.engine.gateway.find(
                model.collection, {}, one_of=(field, selected)
            )
        for identity, data in self.queries[query]:
            key = (model.collection, identity)
            if key not in self.deleted:
                candidates[identity] = self._track(model, key, data)
        for key, record in self.records.items():
            if isinstance(record, model) and key not in self.deleted:
                if record.to_document().get(field) in selected:
                    candidates[key[1]] = record
                else:
                    candidates.pop(key[1], None)
        return list(candidates.values())

    def add(self, record: StoredRecord) -> None:
        self._require_writable()
        allocated_uuid = (
            record.key_fields == ("id",)
            and type(record).assign_identity is StoredRecord.assign_identity
            and getattr(record, record.key_fields[0]) == ""
        )
        record.assign_identity()
        key = (record.collection, document_id(record.identity()))
        if key not in self.expected:
            self.expected[key] = None if allocated_uuid else self.engine.gateway.read(key)
        if (self.expected[key] is not None and key not in self.records) or (
            key in self.records and self.records[key] is not record
        ):
            raise ConflictError("This record already exists")
        self.records[key] = record

    def find(
        self,
        model: type[Record],
        *,
        equal: dict[str, JsonValue] | None = None,
        where: Callable[[Record], bool] | None = None,
        order_by: tuple[str, ...] = (),
        limit: int | None = None,
        offset: int = 0,
        interval: Interval | None = None,
    ) -> Records[Record]:
        rows = self._all(model, equal or {}, interval)
        if where is not None:
            rows = [row for row in rows if where(row)]
        for field in reversed(order_by):
            name = field.removeprefix("-")

            def ordering(row: Record, name: str = name) -> tuple[bool, str | int | float]:
                value: object = getattr(row, name)
                if value is None:
                    return (False, 0)
                if not isinstance(value, str | int | float):
                    raise ValueError("Only scalar fields can order documents")
                return (True, value)

            rows.sort(key=ordering, reverse=field.startswith("-"))
        return Records(rows[offset:] if limit is None else rows[offset : offset + limit])

    def add_all(self, records: list[StoredRecord]) -> None:
        for record in records:
            self.add(record)

    def recent(
        self, model: type[Record], field: str, *, limit: int, offset: int = 0
    ) -> Records[Record]:
        return Records(
            self._track(model, (model.collection, identity), data)
            for identity, data in self.engine.gateway.recent(
                model.collection, field, limit=limit, offset=offset
            )
        )

    def filtered_recent(
        self,
        model: type[Record],
        field: str,
        *,
        limit: int,
        equal: dict[str, JsonValue] | None = None,
        one_of: OneOf | None = None,
    ) -> Records[Record]:
        if one_of is not None and not one_of[1]:
            return Records()
        return Records(
            self._track(model, (model.collection, identity), data)
            for identity, data in self.engine.gateway.recent(
                model.collection, field, limit=limit, equal=equal, one_of=one_of
            )
        )

    def merge(self, record: Record) -> Record:
        self._require_writable()
        key = (record.collection, document_id(record.identity()))
        if key not in self.expected:
            self.expected[key] = self.engine.gateway.read(key)
        self.records[key] = record
        return record

    def window(
        self, model: type[Record], field: str, *, limit: int, after: tuple[int | float, str] | None
    ) -> Records[Record]:
        return Records(
            self._track(model, (model.collection, identity), data)
            for identity, data in self.engine.gateway.window(
                model.collection, field, limit=limit, after=after
            )
        )

    def delete(self, record: StoredRecord) -> None:
        self._require_writable()
        key = (record.collection, document_id(record.identity()))
        if key not in self.expected:
            self.expected[key] = self.engine.gateway.read(key)
        self.deleted.add(key)

    def flush(self) -> None:
        for record in self.records.values():
            record.to_document()

    def connection(self) -> "Session":
        return self

    def commit(self) -> None:
        self._require_writable()
        writes: dict[DocumentKey, Document | None] = {}
        for key, record in self.records.items():
            data = None if key in self.deleted else record.to_document()
            if data != self.expected.get(key):
                writes[key] = data
        for key in self.deleted:
            if self.expected.get(key) is not None:
                writes[key] = None
        if not writes:
            for key in self.deleted:
                self.records.pop(key, None)
                self.hydrated.discard(key)
            if self.deleted:
                self.deleted.clear()
                self.queries.clear()
            return
        self.engine.gateway.commit(self.expected, writes)
        for key, data in writes.items():
            self.expected[key] = data
        for key in self.deleted:
            self.records.pop(key, None)
            self.hydrated.discard(key)
        self.deleted.clear()
        self.queries.clear()

    def rollback(self) -> None:
        self.records.clear()
        self.expected.clear()
        self.deleted.clear()
        self.hydrated.clear()
        self.queries.clear()

    def expunge_all(self) -> None:
        self.rollback()

    def expire_all(self) -> None:
        from job_backend.jobs.models import Job, JobUserRecord

        for record in list(self.records.values()):
            if isinstance(record, Job):
                record.user = self.get(JobUserRecord, record.id)
