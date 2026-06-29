import asyncio
import os
import time
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock

import httpx2
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response

from job_backend.activity.routes import create_router as create_activity_router
from job_backend.auth.middleware import RequireSession
from job_backend.auth.routes import create_router as create_auth_router
from job_backend.auth.sessions import Authenticator
from job_backend.common.environment import load_environment
from job_backend.common.logger import configure_logging, get_logger, shutdown_logging
from job_backend.health.routes import router as health_router
from job_backend.jobs.routes import create_router as create_jobs_router
from job_backend.jobs.user_routes import create_router as create_user_router
from job_backend.matching.routes import create_router as create_matching_router
from job_backend.persistence.database import Database, default_database_path, make_engine, migrate
from job_backend.persistence.errors import ConflictError, DatabaseUnavailableError
from job_backend.persistence.session import Session
from job_backend.profile.routes import create_router as create_profile_router
from job_backend.resumes.routes import create_router as create_resumes_router
from job_backend.scrape.control.routes import create_router as create_control_router
from job_backend.scrape.control.service import ScrapeController
from job_backend.scrape.routes import create_router as create_scrape_router

logger = get_logger(__name__)
_DATABASE_RETRY_SECONDS = 5
_DATABASE_ALERT_INTERVAL_SECONDS = 60
# these still work while postgres is down
_NO_DATABASE_PATHS = {
    "/health",
    "/auth/session",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
}


def create_app(
    state_path: Path | None = None, *, resume_transport: httpx2.BaseTransport | None = None
) -> FastAPI:
    load_environment()
    path = state_path if state_path is not None else default_database_path()
    engine: Database = make_engine(path)
    scrape_controller = ScrapeController(engine)
    database_ready = False
    database_alert_lock = Lock()
    last_database_alert_at: float | None = None

    def report_database_outage(*, startup: bool = False) -> None:
        nonlocal last_database_alert_at
        with database_alert_lock:
            now = time.monotonic()
            if (
                last_database_alert_at is not None
                and now - last_database_alert_at < _DATABASE_ALERT_INTERVAL_SECONDS
            ):
                return
            last_database_alert_at = now
        logger.error(
            "PostgreSQL is unavailable %s. The API remains running; database requests "
            "return HTTP 503. Check the database service and JOB_DATABASE_URL. %s",
            "during API startup" if startup else "while handling an API request",
            "Initialization will retry every 5 seconds." if startup else "Retry the request later.",
            extra={"context": {"event": "database_unavailable"}},
        )

    def initialize_database() -> bool:
        try:
            migrate(engine)
            scrape_controller.recover()
        except DatabaseUnavailableError:
            report_database_outage(startup=True)
            return False
        configure_logging(engine=engine)
        return True

    async def retry_database(stop: asyncio.Event) -> None:
        nonlocal database_ready, last_database_alert_at
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=_DATABASE_RETRY_SECONDS)
            except TimeoutError:
                pass
            if stop.is_set():
                return
            try:
                database_ready = await asyncio.to_thread(initialize_database)
            except Exception:
                logger.exception(
                    "Database initialization failed; database requests remain unavailable"
                )
                return
            if database_ready:
                with database_alert_lock:
                    last_database_alert_at = None
                logger.info("PostgreSQL connection restored; API database initialization completed")
                return

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        nonlocal database_ready
        stop = asyncio.Event()
        retry_task: asyncio.Task[None] | None = None
        try:
            configure_logging()
            database_ready = await asyncio.to_thread(initialize_database)
            if not database_ready:
                retry_task = asyncio.create_task(retry_database(stop))
            logger.info("API started")
            yield
            logger.info("API stopped")
        except Exception:
            logger.exception("API lifecycle failed")
            raise
        finally:
            stop.set()
            if retry_task is not None:
                # let pending connection attempts finish before closing the pool
                await retry_task
            scrape_controller.close()
            shutdown_logging()
            engine.dispose()

    def session_dependency(request: Request) -> Iterator[Session]:
        with Session(engine, read_only=request.method == "GET") as session:
            yield session

    application = FastAPI(title="Intern Radar API", version="0.1.0", lifespan=lifespan)
    application.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=4)

    @application.middleware("http")
    async def wait_for_database(request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.scope["path"][len(request.scope.get("root_path", "")) :]
        if not database_ready and path not in _NO_DATABASE_PATHS:
            return unavailable_response(DatabaseUnavailableError())
        return await call_next(request)

    @application.exception_handler(ConflictError)
    async def conflict_response(_request: Request, error: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @application.exception_handler(DatabaseUnavailableError)
    async def database_response(_request: Request, error: DatabaseUnavailableError) -> JSONResponse:
        report_database_outage()
        return unavailable_response(error)

    def unavailable_response(error: DatabaseUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": str(error), "code": "database_unavailable"},
            headers={"Retry-After": "5"},
        )

    application.include_router(health_router)
    application.include_router(create_profile_router(engine))
    application.include_router(create_activity_router(engine))
    application.include_router(create_jobs_router(session_dependency))
    application.include_router(create_matching_router(engine))
    application.include_router(create_user_router(engine, transport=resume_transport))
    application.include_router(create_resumes_router(engine, transport=resume_transport))
    application.include_router(create_scrape_router(session_dependency))
    application.include_router(create_control_router(engine, scrape_controller))

    authenticator = Authenticator.from_environment()
    if authenticator is not None:
        application.include_router(create_auth_router(authenticator))
        application.add_middleware(RequireSession, authenticator=authenticator)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip().rstrip("/")
            for origin in os.environ.get(
                "JOB_CORS_ORIGINS",
                "http://localhost:4200,http://127.0.0.1:4200,http://[::1]:4200",
            ).split(",")
            if origin.strip()
        ],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        expose_headers=["Content-Disposition", "Retry-After"],
    )
    return application


app = create_app()
