from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.core.scheduler import shutdown_scheduler, start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Off by default on Cloud Run: the CPU is frozen between requests so the
    # interval job cannot be relied on, and every instance would run the daily
    # job concurrently. Use SCHEDULER_ENABLED=true only on an always-on host;
    # otherwise drive /internal/jobs/* from Cloud Scheduler.
    if settings.scheduler_enabled:
        start_scheduler()
    try:
        yield
    finally:
        shutdown_scheduler()


def create_app() -> FastAPI:
    configure_logging()

    application = FastAPI(
        title="Doctor Management Platform API",
        version="0.1.0",
        lifespan=lifespan,
    )

    register_exception_handlers(application)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix="/api/v1")

    media_root = Path(settings.media_root)
    media_root.mkdir(parents=True, exist_ok=True)
    application.mount("/media", StaticFiles(directory=media_root), name="media")

    return application


app = create_app()
