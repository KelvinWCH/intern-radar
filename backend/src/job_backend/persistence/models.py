from collections.abc import Mapping
from dataclasses import dataclass, fields
from functools import cache
from typing import ClassVar, Literal, Protocol
from uuid import uuid4

from pydantic import JsonValue, TypeAdapter

Document = dict[str, JsonValue]

DocumentKey = tuple[str, str]

Interval = tuple[str, int | float | None, int | float | None]

OneOf = tuple[str, list[JsonValue]]


class Gateway(Protocol):
    def read(self, key: DocumentKey) -> Document | None: ...

    def read_many(self, keys: list[DocumentKey]) -> dict[DocumentKey, Document | None]: ...

    def find(
        self,
        collection: str,
        equal: Mapping[str, JsonValue],
        *,
        interval: Interval | None = None,
        one_of: OneOf | None = None,
    ) -> list[tuple[str, Document]]: ...

    def commit(
        self,
        expected: Mapping[DocumentKey, Document | None],
        writes: Mapping[DocumentKey, Document | None],
    ) -> None: ...

    def recent(
        self,
        collection: str,
        field: str,
        *,
        limit: int,
        offset: int = 0,
        equal: Mapping[str, JsonValue] | None = None,
        one_of: OneOf | None = None,
    ) -> list[tuple[str, Document]]: ...

    def select(
        self, query: "ReadQuery", *, limit: int, offset: int = 0, count: bool = True
    ) -> "ReadPage": ...

    def groups(
        self, query: "ReadQuery", fields: tuple[str, ...], sums: tuple[str, ...] = ()
    ) -> list[Document]: ...

    def values(self, query: "ReadQuery", field: str) -> list[str]: ...

    def close(self) -> None: ...

    def window(
        self, collection: str, field: str, *, limit: int, after: tuple[int | float, str] | None
    ) -> list[tuple[str, Document]]: ...


_OBJECT = TypeAdapter(dict[str, JsonValue])


@dataclass(kw_only=True)
class StoredRecord:
    collection: ClassVar[str]
    key_fields: ClassVar[tuple[str, ...]]

    def assign_identity(self) -> None:
        if self.key_fields == ("id",):
            name = self.key_fields[0]
            if getattr(self, name) == "":
                setattr(self, name, str(uuid4()))

    def to_document(self) -> dict[str, JsonValue]:
        return _OBJECT.validate_python(
            {
                field.name: getattr(self, field.name)
                for field in fields(self)
                if field.name not in {"user", "documents"}
            }
        )

    def identity(self) -> tuple[str | int, ...]:
        values: list[str | int] = []
        for name in self.key_fields:
            value: object = getattr(self, name)
            if not isinstance(value, str | int) or isinstance(value, bool) or value in ("", 0):
                raise ValueError(f"Invalid primary key for {self.collection}")
            values.append(value)
        return tuple(values)


@cache
def record_adapter(model: type[StoredRecord]) -> TypeAdapter[StoredRecord]:
    return TypeAdapter(model)


@dataclass(frozen=True)
class Filter:
    field: str
    op: Literal["eq", "ne", "in", "ge", "gt", "lt", "le", "contains"] = "eq"
    value: JsonValue = None


@dataclass(frozen=True)
class Junction:
    children: tuple["Filter | Junction", ...] = ()
    mode: Literal["and", "or"] = "and"


@dataclass(frozen=True)
class Order:
    field: str
    descending: bool = False
    numeric: bool = False
    ranks: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class ReadQuery:
    collection: str
    where: Filter | Junction = Junction()
    order: tuple[Order, ...] = ()
    fields: tuple[str, ...] | None = None
    source: bool = False
    timezone: str = "UTC"
    distinct: str | None = None
    lead: tuple[Order, ...] = ()


@dataclass
class ReadPage:
    items: list[Document]
    total: int | None
