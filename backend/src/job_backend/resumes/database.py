from collections.abc import Generator
from contextlib import contextmanager

from job_backend.persistence.database import (
    Database,
    default_database_path,
    make_engine,
    migrate,
)


@contextmanager
def resume_database(engine: Database | None) -> Generator[Database, None, None]:
    if engine is not None:
        yield engine
        return
    owned = make_engine(default_database_path())
    try:
        migrate(owned)
        yield owned
    finally:
        owned.dispose()
