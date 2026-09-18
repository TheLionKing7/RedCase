"""POST /v1/internal/sweep tests — Task 1.7 deploy architecture.

Auth contract: shared INTERNAL_SWEEP_TOKEN, constant-time compared, fails
CLOSED when unprovisioned. Scope: platform maintenance (deferred-embedding
backfill) as the service role — never a tenant-facing route.
"""

import uuid

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

import app.routers.internal as internal_module
from app.config import Settings
from app.ingestion.db import EMBEDDING_DIMS, ingest_pdf
from app.main import create_app
from tests.pdf_factory import make_pdf, synthetic_judgment_pages

VAULT_JURIS_NG = uuid.UUID("b0000001-0000-4000-8000-000000000001")
SWEEP_TOKEN = "test-sweep-token-not-a-real-secret"  # noqa: S105 (throwaway test secret)


class ConstantEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.5] * EMBEDDING_DIMS for _ in texts]


async def _ingest_null_embedded(app_db_url: str, tmp_path) -> None:
    pdf = make_pdf(tmp_path / f"sweep-{uuid.uuid4().hex[:8]}.pdf", synthetic_judgment_pages())
    conn = await asyncpg.connect(app_db_url)
    try:
        await ingest_pdf(
            conn,
            tenant_id=uuid.UUID(SEED_TENANT_AETOES),
            vault_id=VAULT_JURIS_NG,
            pdf_path=pdf,
            embedder=None,  # deferred-embed path: chunk lands with embedding NULL
        )
    finally:
        await conn.close()


def _client(app_db_url: str, *, token: str | None = SWEEP_TOKEN) -> TestClient:
    settings = Settings(
        _env_file=None,
        database_url=app_db_url,
        internal_sweep_token=token,
    )
    return TestClient(create_app(settings))


class TestInternalSweep:
    async def test_missing_token_refused(self, app_db_url: str) -> None:
        resp = _client(app_db_url).post("/v1/internal/sweep")
        assert resp.status_code == 403

    async def test_wrong_token_refused(self, app_db_url: str) -> None:
        resp = _client(app_db_url).post(
            "/v1/internal/sweep", headers={"X-Internal-Token": "not-the-token"}
        )
        assert resp.status_code == 403

    async def test_unprovisioned_token_fails_closed(self, app_db_url: str) -> None:
        resp = _client(app_db_url, token=None).post(
            "/v1/internal/sweep", headers={"X-Internal-Token": SWEEP_TOKEN}
        )
        assert resp.status_code == 403

    async def test_sweep_backfills_null_chunks(
        self, app_db_url: str, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        await _ingest_null_embedded(app_db_url, tmp_path)
        monkeypatch.setattr(internal_module, "make_embedder", lambda s: ConstantEmbedder())
        with _client(app_db_url) as client:  # lifespan creates the pool
            resp = client.post(
                "/v1/internal/sweep", headers={"X-Internal-Token": SWEEP_TOKEN}
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["pending"] >= 1
        assert body["embedded"] == body["pending"]

        conn = await asyncpg.connect(app_db_url)
        try:
            # Verification runs as the non-superuser app role, so it must
            # honour the same RLS contract as the sweep (PG16 placeholder
            # GUC via set_config inside a transaction).
            async with conn.transaction():
                await conn.fetchval(
                    "SELECT set_config('app.tenant_id', $1, true)",
                    SEED_TENANT_AETOES,
                )
                remaining = await conn.fetchval(
                    "SELECT count(*) FROM document_chunks WHERE embedding IS NULL"
                )
        finally:
            await conn.close()
        assert remaining == 0
