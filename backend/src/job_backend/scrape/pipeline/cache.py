import sqlite3
import time
import zlib
from collections.abc import Generator
from contextlib import closing, contextmanager
from typing import TypeVar

from pydantic import TypeAdapter

from job_backend.common.logger import get_logger
from job_backend.persistence.database import Database
from job_backend.persistence.identity import document_id
from job_backend.persistence.models import StoredRecord, record_adapter
from job_backend.scrape.pipeline.constants import MAX_CACHE_BYTES

Record = TypeVar("Record", bound=StoredRecord)
_ROW = TypeAdapter(tuple[bytes, float, float])
_TOTAL = TypeAdapter(tuple[int])
_KEYS = TypeAdapter(list[tuple[str, str, int]])
logger = get_logger(__name__)


class ScrapeCache:
    def __init__(self, engine: Database) -> None:
        self.path = engine.local_path.with_name(engine.local_path.name + ".cache.sqlite3")

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS entries ("
                "collection TEXT NOT NULL, key TEXT NOT NULL, payload BLOB NOT NULL, "
                "expires_at REAL NOT NULL, written_at REAL NOT NULL, "
                "PRIMARY KEY (collection, key))"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS expiry ON entries(expires_at)")
            yield connection

    def get(
        self,
        model: type[Record],
        identity: tuple[str | int, ...],
        *,
        ttl_seconds: float,
    ) -> Record | None:
        if ttl_seconds <= 0:
            return None
        key = document_id(identity)
        now = time.time()
        try:
            if self.path.exists():
                with self._connect() as connection:
                    row: object = connection.execute(
                        "SELECT payload, expires_at, written_at FROM entries "
                        "WHERE collection = ? AND key = ?",
                        (model.collection, key),
                    ).fetchone()
                if row is not None:
                    payload, expires_at, written_at = _ROW.validate_python(row)
                    if written_at <= now < min(expires_at, written_at + ttl_seconds):
                        record = record_adapter(model).validate_json(zlib.decompress(payload))
                        if isinstance(record, model) and record.identity() == identity:
                            return record
        except (OSError, sqlite3.Error, ValueError, zlib.error) as error:
            logger.warning(
                "Local scrape cache read failed (%s); retrying source", type(error).__name__
            )
        return None

    def put(self, record: StoredRecord, *, ttl_seconds: float) -> None:
        self._put(record, ttl_seconds=ttl_seconds, written_at=time.time())

    def _put(self, record: StoredRecord, *, ttl_seconds: float, written_at: float) -> None:
        if ttl_seconds <= 0:
            return
        payload = zlib.compress(record_adapter(type(record)).dump_json(record))
        if len(payload) > MAX_CACHE_BYTES:
            return
        now = time.time()
        try:
            with self._connect() as connection:
                connection.execute("DELETE FROM entries WHERE expires_at <= ?", (now,))
                connection.execute(
                    "INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?, ?)",
                    (
                        record.collection,
                        document_id(record.identity()),
                        payload,
                        written_at + ttl_seconds,
                        written_at,
                    ),
                )
                size_row: object = connection.execute(
                    "SELECT COALESCE(SUM(LENGTH(payload)), 0) FROM entries"
                ).fetchone()
                total = _TOTAL.validate_python(size_row)[0]
                if total > MAX_CACHE_BYTES:
                    rows: object = connection.execute(
                        "SELECT collection, key, LENGTH(payload) FROM entries ORDER BY written_at"
                    ).fetchall()
                    for collection, key, size in _KEYS.validate_python(rows):
                        if total <= MAX_CACHE_BYTES:
                            break
                        connection.execute(
                            "DELETE FROM entries WHERE collection = ? AND key = ?",
                            (collection, key),
                        )
                        total -= size
        except (OSError, sqlite3.Error) as error:
            logger.warning(
                "Local scrape cache write failed (%s); result retained in this import",
                type(error).__name__,
            )
