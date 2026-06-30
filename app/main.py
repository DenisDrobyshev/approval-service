"""FastAPI application factory and operational endpoints."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from sqlalchemy import text

from .api.routes_approvals import router as approvals_router
from .config import get_settings
from .database import Base, engine
from .errors import register_exception_handlers
from .logging_config import configure_logging
from .schemas import HealthResponse

logger = logging.getLogger("approval.access")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.auto_create_tables:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="Content approval workflow service",
        lifespan=lifespan,
    )

    register_exception_handlers(app)

    @app.middleware("http")
    async def access_log_middleware(request: Request, call_next):
        # Correlation id; never log headers or bodies (they can carry tokens).
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "%s %s -> %s (%.1fms) request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response

    @app.get("/health", response_model=HealthResponse, tags=["ops"])
    async def health() -> HealthResponse:
        """Liveness: the process is up and serving."""
        return HealthResponse(
            status="ok", service=settings.app_name, version=settings.app_version
        )

    @app.get("/ready", tags=["ops"])
    async def ready() -> Response:
        """Readiness: dependencies (the database) are reachable."""
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            logger.warning("Readiness check failed: database unreachable")
            return Response(
                content='{"status":"not_ready"}',
                media_type="application/json",
                status_code=503,
            )
        return Response(
            content='{"status":"ready"}',
            media_type="application/json",
            status_code=200,
        )

    app.include_router(approvals_router)
    return app


app = create_app()
