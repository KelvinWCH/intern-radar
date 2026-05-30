from collections.abc import Mapping
from copy import deepcopy
from threading import RLock

from pydantic import JsonValue

from job_backend.persistence.errors import ConflictError
from job_backend.persistence.models import (
    Document,
    DocumentKey,
    Interval,
    OneOf,
    ReadPage,
    ReadQuery,
)
from tests import projected_memory


class MemoryGateway:
    def __init__(self) -> None:
        self.documents: dict[DocumentKey, Document] = {}
        self.lock = RLock()

    def read(self, key: DocumentKey) -> Document | None:
        with self.lock:
            return deepcopy(self.documents.get(key))

    def read_many(self, keys: list[DocumentKey]) -> dict[DocumentKey, Document | None]:
        with self.lock:
            return {key: deepcopy(self.documents.get(key)) for key in keys}

    def find(
        self,
        collection: str,
        equal: Mapping[str, object],
        *,
        interval: Interval | None = None,
        one_of: OneOf | None = None,
    ) -> list[tuple[str, Document]]:
        with self.lock:
            rows = [
                (key[1], deepcopy(data))
                for key, data in self.documents.items()
                if key[0] == collection
                and all(data.get(field) == value for field, value in equal.items())
            ]
            if one_of is not None:
                rows = [(key, data) for key, data in rows if data.get(one_of[0]) in one_of[1]]
            if interval is not None:
                field, start, end = interval
                rows = [
                    (key, data)
                    for key, data in rows
                    if isinstance(value := data.get(field), int | float)
                    and (start is None or value >= start)
                    and (end is None or value < end)
                ]
            return rows

    def commit(
        self,
        expected: Mapping[DocumentKey, Document | None],
        writes: Mapping[DocumentKey, Document | None],
    ) -> None:
        with self.lock:
            if any(self.documents.get(key) != data for key, data in expected.items()):
                raise ConflictError("Saved data changed")
            for key, data in writes.items():
                if data is None:
                    self.documents.pop(key, None)
                else:
                    self.documents[key] = deepcopy(data)

    def recent(
        self,
        collection: str,
        field: str,
        *,
        limit: int,
        offset: int = 0,
        equal: Mapping[str, JsonValue] | None = None,
        one_of: OneOf | None = None,
    ) -> list[tuple[str, Document]]:
        if limit < 1 or offset < 0:
            raise ValueError("Pagination requires a positive limit and nonnegative offset")
        with self.lock:
            rows = [
                (key[1], deepcopy(data))
                for key, data in self.documents.items()
                if key[0] == collection
                and all(data.get(name) == value for name, value in (equal or {}).items())
                and (one_of is None or data.get(one_of[0]) in one_of[1])
            ]

            def ordering(row: tuple[str, Document]) -> tuple[int | float, str]:
                value = row[1][field]
                if not isinstance(value, int | float):
                    raise ValueError("History ordering requires a numeric field")
                return value, row[0]

            rows.sort(key=ordering, reverse=True)
            return rows[offset : offset + limit]

    def window(
        self, collection: str, field: str, *, limit: int, after: tuple[int | float, str] | None
    ) -> list[tuple[str, Document]]:
        with self.lock:
            ordered: list[tuple[int | float, str, Document]] = []
            for (name, identity), data in self.documents.items():
                value = data.get(field)
                if name == collection and isinstance(value, int | float):
                    if after is None or (value, identity) < after:
                        ordered.append((value, identity, data))
            ordered.sort(key=lambda item: (item[0], item[1]), reverse=True)
            return [(identity, deepcopy(data)) for _, identity, data in ordered[:limit]]

    def select(
        self, query: ReadQuery, *, limit: int, offset: int = 0, count: bool = True
    ) -> ReadPage:
        with self.lock:
            return projected_memory.select(
                self.documents, query, limit=limit, offset=offset, count=count
            )

    def groups(
        self, query: ReadQuery, fields: tuple[str, ...], sums: tuple[str, ...] = ()
    ) -> list[Document]:
        with self.lock:
            return projected_memory.groups(self.documents, query, fields, sums)

    def values(self, query: ReadQuery, field: str) -> list[str]:
        with self.lock:
            found = {
                str(found)
                for key, data in projected_memory.rows(self.documents, query)
                if (found := projected_memory.value(data, key, field, query, self.documents))
                is not None
            }
            return sorted(found)

    def close(self) -> None: ...
