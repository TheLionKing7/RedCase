"""FastAPI app factory (Task 1.1; HANDOFF.md 1, Phase1-Design 3.1).

Boot contract:
- structlog with the mandatory ZDR redaction filter is configured exactly once,
  before any route is served (HANDOFF.md 2.1).
- The app mounts under /v1/* (and later /v1/slack/*, Phase 2). Task 1.1
  registers the API skeleton only; /v1/query lands in Task 1.4.
- Secrets are NOT required to boot (see config.Settings); code paths that need
  them call Settings.require_secrets() at use time.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.config import Settings, get_settings
from app.middleware.zdr import configure_logging, get_logger

log = get_logger("redcase.boot")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log.info(
        "api_starting",
        env=settings.env,
        app=settings.app_name,
        embed_model=settings.embed_model,
    )
    yield
    log.info("api_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the RedCase API application. `settings` is injectable for tests."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.include_router(_v1_router())
    return app


def _v1_router() -> APIRouter:
    """API skeleton (Task 1.1). Endpoints are added per task from Task 1.4 on."""
    router = APIRouter(prefix="/v1")

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return router


app = create_app()
