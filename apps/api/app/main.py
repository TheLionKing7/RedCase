"""FastAPI app factory (Task 1.1; HANDOFF.md 1, Phase1-Design 3.1).

Boot contract:
- structlog with the mandatory ZDR redaction filter is configured exactly once,
  before any route is served (HANDOFF.md 2.1).
- The app mounts under /v1/* (and later /v1/slack/*, Phase 2). /v1/query
  landed in Task 1.4.
- Secrets are NOT required to boot (see config.Settings); code paths that need
  them call Settings.require_secrets() or surface 503 at use time.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncpg
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.middleware.zdr import configure_logging, get_logger
from app.routers.analyses import router as analyses_router
from app.routers.audit import router as audit_router
from app.routers.channels import router as channels_router
from app.routers.conflicts import router as conflicts_router
from app.routers.expert_chat import router as expert_chat_router
from app.routers.internal import router as internal_router
from app.routers.invoicing import router as invoicing_router
from app.routers.practice import router as practice_router
from app.routers.query import router as query_router
from app.routers.router import router as dual_query_router
from app.routers.vault_a import router as vault_a_router

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
    pool: asyncpg.Pool | None = None
    if settings.database_url:
        pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10)
    else:
        log.warn("api_no_database", note="database_url unset — /v1/query returns 503")
    app.state.db_pool = pool
    yield
    if pool is not None:
        await pool.close()
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

    # Dev CORS for the apps/web vite dev server (7100). Locked down to the
    # configured origin list; production serves the frontend same-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["POST", "GET"],
        allow_headers=["authorization", "content-type"],
    )

    app.include_router(_v1_router())
    app.include_router(query_router)
    app.include_router(analyses_router)
    app.include_router(channels_router)
    app.include_router(conflicts_router)
    app.include_router(audit_router)
    app.include_router(expert_chat_router)
    app.include_router(internal_router)
    app.include_router(vault_a_router)
    app.include_router(practice_router)
    app.include_router(invoicing_router)
    app.include_router(dual_query_router)
    return app


def _v1_router() -> APIRouter:
    router = APIRouter(prefix="/v1")

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return router


app = create_app()
