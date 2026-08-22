import os
from pathlib import Path

from job_backend.common.environment import load_environment
from job_backend.persistence.models import Gateway
from job_backend.persistence.postgres import PostgresGateway


def default_database_path() -> Path:
    load_environment()
    directory = Path(os.environ.get("JOB_DATA_DIR", "data")).expanduser()
    if not directory.is_absolute():
        directory = Path(__file__).resolve().parents[3] / directory
    return directory.resolve() / "postgres"


class Database:
    def __init__(
        self, gateway: Gateway, local_path: Path, *, connection_url: str | None = None
    ) -> None:
        self.connection_url = connection_url
        self.gateway = gateway
        self.local_path = local_path.expanduser().resolve()

    def dispose(self) -> None:
        self.gateway.close()


def make_engine(state_path: Path | None = None, *, connection_url: str | None = None) -> Database:
    load_environment()
    path = state_path or default_database_path()
    url = connection_url or os.environ.get("JOB_DATABASE_URL", "").strip() or None
    gateway = _open_gateway(path) if connection_url is None else _open_gateway(path, connection_url)
    return Database(gateway, path, connection_url=url)


def _open_gateway(_path: Path, connection_url: str | None = None) -> Gateway:
    return PostgresGateway(connection_url)


def migrate(engine: Database) -> None:
    if isinstance(engine.gateway, PostgresGateway):
        engine.gateway.initialize()
