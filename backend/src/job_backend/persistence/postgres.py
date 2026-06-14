import hashlib
import json
import os
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from importlib.resources import files
from threading import Lock

from psycopg import Connection, OperationalError, sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import tuple_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool, PoolTimeout
from pydantic import JsonValue, TypeAdapter

from job_backend.common.environment import load_environment
from job_backend.persistence import projected_sql
from job_backend.persistence.errors import ConflictError, DatabaseUnavailableError
from job_backend.persistence.models import (
    Document,
    DocumentKey,
    Interval,
    OneOf,
    ReadPage,
    ReadQuery,
)

_DOCUMENT = TypeAdapter(Document)
_ROW = TypeAdapter(tuple[str, Document])
_KEYED_ROW = TypeAdapter(tuple[str, str, Document])
_MIGRATION_ROW = TypeAdapter(tuple[str, str])
_MIGRATION_LOCK = 7907195807835130
_RECORD_LOCK_NAMESPACE = 20270001
_RECORD_LOCK_STRIPES = 256
POOL_SIZE = 4
POOL_TIMEOUT_SECONDS = 10
STATEMENT_TIMEOUT_MS = 30_000


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def _jsonb(value: object) -> Jsonb:
    return Jsonb(value, dumps=_json)


def _number(field: str) -> sql.Composed:
    return sql.SQL(
        "(CASE WHEN jsonb_typeof(data -> {field}) = 'number' THEN (data ->> {field})::numeric END)"
    ).format(field=sql.Literal(field))


def _predicates(
    collection: str,
    equal: Mapping[str, JsonValue],
    interval: Interval | None = None,
    one_of: OneOf | None = None,
) -> tuple[sql.Composed, list[object]]:
    clauses: list[sql.Composable] = [sql.SQL("collection = %s")]
    parameters: list[object] = [collection]
    for field, value in equal.items():
        expression = sql.SQL("data -> {}").format(sql.Literal(field))
        if value is None:
            clauses.append(
                sql.SQL("COALESCE({}, 'null'::jsonb) = 'null'::jsonb").format(expression)
            )
        else:
            clauses.append(sql.SQL("{} = %s::jsonb").format(expression))
            parameters.append(_jsonb(value))
    if interval is not None:
        field, start, end = interval
        clauses.append(sql.SQL("jsonb_typeof(data -> {}) = 'number'").format(sql.Literal(field)))
        if start is not None:
            clauses.append(sql.SQL("{} >= %s").format(_number(field)))
            parameters.append(start)
        if end is not None:
            clauses.append(sql.SQL("{} < %s").format(_number(field)))
            parameters.append(end)
    if one_of is not None:
        field, values = one_of
        expression = sql.SQL("data -> {}").format(sql.Literal(field))
        condition = sql.SQL("{} = ANY(%s::jsonb[])").format(expression)
        parameters.append([_jsonb(value) for value in values if value is not None])
        if None in values:
            condition = sql.SQL("({} OR COALESCE({}, 'null'::jsonb) = 'null'::jsonb)").format(
                condition, expression
            )
        clauses.append(condition)
    return sql.SQL(" AND ").join(clauses), parameters


def _lock_id(key: DocumentKey) -> int:
    digest = hashlib.blake2b(_json(key).encode(), digest_size=8, person=b"job-record-lock").digest()
    return int.from_bytes(digest, "big") % _RECORD_LOCK_STRIPES


class PostgresGateway:
    def __init__(self, connection_url: str | None = None) -> None:
        self._connection_url = connection_url
        self._pool: ConnectionPool[Connection[tuple[object, ...]]] | None = None
        self._pool_lock = Lock()
        self._migration_lock = Lock()
        self._initialized = False

    def _get_pool(self) -> ConnectionPool[Connection[tuple[object, ...]]]:
        with self._pool_lock:
            if self._pool is None:
                load_environment()
                url = self._connection_url or os.environ.get("JOB_DATABASE_URL", "").strip()
                if not url:
                    raise ValueError("Set JOB_DATABASE_URL before starting PostgreSQL storage")
                options = conninfo_to_dict(url).get("options", "")
                self._pool = ConnectionPool(
                    url,
                    connection_class=Connection[tuple[object, ...]],
                    kwargs={
                        "row_factory": tuple_row,
                        "autocommit": True,
                        "connect_timeout": POOL_TIMEOUT_SECONDS,
                        "options": f"{options} -c statement_timeout={STATEMENT_TIMEOUT_MS}".strip(),
                        "application_name": "intern-radar",
                    },
                    min_size=0,
                    max_size=POOL_SIZE,
                    timeout=POOL_TIMEOUT_SECONDS,
                    open=False,
                )
                self._pool.open()
            return self._pool

    @contextmanager
    def _connection(self) -> Generator[Connection[tuple[object, ...]]]:
        try:
            with self._get_pool().connection() as connection:
                yield connection
        except (OperationalError, PoolTimeout) as error:
            raise DatabaseUnavailableError() from error

    def initialize(self) -> None:
        with self._migration_lock:
            if self._initialized:
                return
            with self._connection() as connection, connection.transaction():
                connection.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK,))
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS job_schema_migrations ("
                    "name text PRIMARY KEY, checksum text NOT NULL, "
                    "applied_at timestamptz NOT NULL DEFAULT clock_timestamp())"
                )
                applied = dict(
                    _MIGRATION_ROW.validate_python(row, strict=True)
                    for row in connection.execute(
                        "SELECT name, checksum FROM job_schema_migrations"
                    ).fetchall()
                )
                migrations = sorted(
                    (
                        item
                        for item in files("job_backend.persistence").joinpath("sql").iterdir()
                        if item.name.endswith(".sql")
                    ),
                    key=lambda item: item.name,
                )
                known = {item.name for item in migrations}
                if set(applied) - known:
                    raise RuntimeError("PostgreSQL schema is newer than this application")
                for migration in migrations:
                    source = migration.read_text(encoding="utf-8")
                    checksum = hashlib.sha256(source.encode()).hexdigest()
                    if migration.name in applied:
                        if applied[migration.name] != checksum:
                            raise RuntimeError(f"Applied SQL migration changed: {migration.name}")
                        continue
                    connection.execute(source.encode(), prepare=False)
                    connection.execute(
                        "INSERT INTO job_schema_migrations(name, checksum) VALUES (%s, %s)",
                        (migration.name, checksum),
                    )
            self._initialized = True

    def read(self, key: DocumentKey) -> Document | None:
        return self.read_many([key])[key]

    def read_many(self, keys: list[DocumentKey]) -> dict[DocumentKey, Document | None]:
        unique = list(dict.fromkeys(keys))
        if not unique:
            return {}
        self.initialize()
        result: dict[DocumentKey, Document | None] = dict.fromkeys(unique)
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT records.collection, records.key, records.data FROM job_records records "
                "JOIN unnest(%s::text[], %s::text[]) requested(collection, key) "
                "ON (records.collection, records.key) = (requested.collection, requested.key)",
                ([key[0] for key in unique], [key[1] for key in unique]),
            ).fetchall()
        for row in rows:
            collection, identity, data = _KEYED_ROW.validate_python(row, strict=True)
            result[collection, identity] = data
        return result

    def find(
        self,
        collection: str,
        equal: Mapping[str, JsonValue],
        *,
        interval: Interval | None = None,
        one_of: OneOf | None = None,
    ) -> list[tuple[str, Document]]:
        if one_of is not None and not one_of[1]:
            return []
        self.initialize()
        where, parameters = _predicates(collection, equal, interval, one_of)
        query = sql.SQL("SELECT key, data FROM job_records WHERE {} ORDER BY key").format(where)
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_ROW.validate_python(row, strict=True) for row in rows]

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
        if one_of is not None and not one_of[1]:
            return []
        self.initialize()
        where, parameters = _predicates(collection, equal or {}, (field, None, None), one_of)
        query = sql.SQL(
            "SELECT key, data FROM job_records WHERE {} "
            "ORDER BY {} DESC, key DESC LIMIT %s OFFSET %s"
        ).format(where, _number(field))
        parameters.extend([limit, offset])
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_ROW.validate_python(row, strict=True) for row in rows]

    def window(
        self, collection: str, field: str, *, limit: int, after: tuple[int | float, str] | None
    ) -> list[tuple[str, Document]]:
        if not 1 <= limit <= 101:
            raise ValueError("Cursor windows contain at most 101 records")
        self.initialize()
        where, parameters = _predicates(collection, {}, (field, None, None))
        if after is not None:
            where += sql.SQL(" AND ({}, key) < (%s, %s)").format(_number(field))
            parameters.extend(after)
        query = sql.SQL(
            "SELECT key, data FROM job_records WHERE {} ORDER BY {} DESC, key DESC LIMIT %s"
        ).format(where, _number(field))
        parameters.append(limit)
        with self._connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [_ROW.validate_python(row, strict=True) for row in rows]

    def commit(
        self,
        expected: Mapping[DocumentKey, Document | None],
        writes: Mapping[DocumentKey, Document | None],
    ) -> None:
        if not set(writes).issubset(expected):
            raise ValueError("Every write must have a snapshot precondition")
        changed = {key: data for key, data in writes.items() if _json(data) != _json(expected[key])}
        if not changed:
            return
        for data in [*expected.values(), *changed.values()]:
            if data is not None:
                _DOCUMENT.validate_python(data, strict=True)
                _json(data)
        snapshots = [
            {"collection": key[0], "key": key[1], "data": data} for key, data in expected.items()
        ]
        saved = [
            {"collection": key[0], "key": key[1], "data": data}
            for key, data in changed.items()
            if data is not None
        ]
        deleted = [key for key, data in changed.items() if data is None]
        self.initialize()
        with self._connection() as connection, connection.transaction():
            connection.execute(
                "SELECT pg_advisory_xact_lock(%s, lock_id) FROM "
                "(SELECT unnest(%s::integer[]) AS lock_id ORDER BY lock_id) locks",
                (_RECORD_LOCK_NAMESPACE, sorted({_lock_id(key) for key in expected})),
            )
            mismatch = connection.execute(
                "SELECT 1 FROM jsonb_to_recordset(%s::jsonb) "
                "expected(collection text, key text, data jsonb) "
                "LEFT JOIN job_records records USING (collection, key) "
                "WHERE records.data IS DISTINCT FROM expected.data LIMIT 1",
                (_jsonb(snapshots),),
            ).fetchone()
            if mismatch is not None:
                raise ConflictError("Saved data changed. Reload and retry the operation.")
            if saved:
                connection.execute(
                    "INSERT INTO job_records(collection, key, data) "
                    "SELECT collection, key, data FROM jsonb_to_recordset(%s::jsonb) "
                    "changed(collection text, key text, data jsonb) "
                    "ON CONFLICT (collection, key) DO UPDATE "
                    "SET data = EXCLUDED.data, updated_at = clock_timestamp() "
                    "WHERE job_records.data IS DISTINCT FROM EXCLUDED.data",
                    (_jsonb(saved),),
                )
            if deleted:
                connection.execute(
                    "DELETE FROM job_records records USING "
                    "unnest(%s::text[], %s::text[]) deleted(collection, key) "
                    "WHERE (records.collection, records.key) = (deleted.collection, deleted.key)",
                    ([key[0] for key in deleted], [key[1] for key in deleted]),
                )

    def select(
        self, query: ReadQuery, *, limit: int, offset: int = 0, count: bool = True
    ) -> ReadPage:
        self.initialize()
        with self._connection() as connection:
            return projected_sql.select_page(
                connection, query, limit=limit, offset=offset, count=count
            )

    def groups(
        self, query: ReadQuery, fields: tuple[str, ...], sums: tuple[str, ...] = ()
    ) -> list[Document]:
        self.initialize()
        with self._connection() as connection:
            return projected_sql.grouped(connection, query, fields, sums)

    def values(self, query: ReadQuery, field: str) -> list[str]:
        self.initialize()
        with self._connection() as connection:
            return projected_sql.distinct_values(connection, query, field)

    def close(self) -> None:
        with self._pool_lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None
        self._initialized = False
