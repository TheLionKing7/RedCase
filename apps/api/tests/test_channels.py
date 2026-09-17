"""Channels tests — Feature-Addendum §7 (Core tier).

DoD under test (owner 2026-09-17): channels + channel_messages schema
with RLS; matter channels auto-provision via provision_matter_channel
(Slack convention '#case-{a}-v-{b}', idempotent); POST
/v1/channels/{id}/messages stores a tenant-scoped message with validated
attachment references.

Seed contract: migration 0005 seeds aetoes' firm-wide '#general' channel
under the fixed id GENERAL_CHANNEL. ZDR: messages reference documents/
analyses; they never hold document content.
"""

import asyncio
import uuid

import asyncpg
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

from app.config import Settings
from app.ingestion.db import EMBEDDING_DIMS, ingest_pdf
from app.main import create_app
from tests.pdf_factory import make_pdf, synthetic_judgment_pages
from tests.test_query_api import make_jwt

GENERAL_CHANNEL = "c0000001-0000-4000-8000-000000000001"
VAULT_JURIS_NG = uuid.UUID("b0000001-0000-4000-8000-000000000001")
JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105 (throwaway test secret)


class ConstantEmbedder:
    def __init__(self, value: float = 0.5) -> None:
        self.value = value

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[self.value] * EMBEDDING_DIMS for _ in texts]


def _settings(app_db_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=app_db_url,
        supabase_jwt_secret=JWT_SECRET,
    )


def _auth(tenant: str = SEED_TENANT_AETOES) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_jwt(tenant=tenant)}"}


async def _ingest_doc(app_db_url: str, tmp_path, tenant: str) -> uuid.UUID:
    n = int(uuid.uuid4().hex[:6], 16)
    citation = f"(2002) {1 + n % 9} NWLR (Pt. {150 + n % 700}) {1 + n % 400}"
    pages = synthetic_judgment_pages()
    pages[0] = [citation if "NWLR CITATION" in line else line for line in pages[0]]
    pdf = make_pdf(tmp_path / f"channels-{n}.pdf", pages)
    conn = await asyncpg.connect(app_db_url)
    try:
        result = await ingest_pdf(
            conn,
            tenant_id=uuid.UUID(tenant),
            vault_id=VAULT_JURIS_NG,
            pdf_path=pdf,
            embedder=ConstantEmbedder(),
        )
    finally:
        await conn.close()
    return result.document_id


async def _provision_tenant(app_db_url: str) -> str:
    tid, vid = str(uuid.uuid4()), str(uuid.uuid4())
    conn = await asyncpg.connect(app_db_url)
    try:
        await conn.execute(
            "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
            uuid.UUID(tid),
            f"Tenant {tid[:8]}",
            f"t-{tid[:8]}",
        )
        await conn.execute(
            "INSERT INTO vaults (id, tenant_id, vault_type, name)"
            " VALUES ($1, $2, 'juris', 'Vault')",
            uuid.UUID(vid),
            uuid.UUID(tid),
        )
    finally:
        await conn.close()
    return tid


async def _provision_matter_channel(
    app_db_url: str,
    tenant: str,
    claimant: str,
    defendant: str,
    matter_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, str]:
    matter_id = matter_id or uuid.uuid4()
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tenant
            )
            row = await conn.fetchrow(
                "SELECT provision_matter_channel($1, $2, $3, $4) AS id",
                uuid.UUID(tenant),
                matter_id,
                claimant,
                defendant,
            )
            chan = await conn.fetchrow(
                "SELECT name FROM channels WHERE id = $1", row["id"]
            )
    finally:
        await conn.close()
    return row["id"], chan["name"]


class TestProvisionMatterChannel:
    def test_slack_convention_name_and_idempotency(self, app_db_url: str) -> None:
        matter = uuid.uuid4()
        chan_id, name = asyncio.run(
            _provision_matter_channel(
                app_db_url, SEED_TENANT_AETOES, "FBN", "Aetoes", matter
            )
        )
        assert name == "#case-fbn-v-aetoes"
        again_id, again_name = asyncio.run(
            _provision_matter_channel(
                app_db_url, SEED_TENANT_AETOES, "FBN", "Aetoes", matter
            )
        )
        # Idempotent: same matter + parties returns the SAME channel.
        assert again_id == chan_id
        assert again_name == name

    def test_sanitizes_party_names(self, app_db_url: str) -> None:
        _, name = asyncio.run(
            _provision_matter_channel(
                app_db_url, SEED_TENANT_AETOES, "Ade & Sons Ltd.", "F.R.N."
            )
        )
        assert name == "#case-ade-sons-ltd-v-f-r-n"


class TestPostMessage:
    def test_post_to_firm_channel(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/channels/{GENERAL_CHANNEL}/messages",
                json={"body": "Kickoff call moved to 4pm."},
                headers=_auth(),
            )
        assert resp.status_code == 201
        body = resp.json()
        assert uuid.UUID(body["id"])
        assert body["channel_id"] == GENERAL_CHANNEL

    def test_foreign_channel_not_visible(self, app_db_url: str) -> None:
        tid = asyncio.run(_provision_tenant(app_db_url))
        chan_id, _ = asyncio.run(
            _provision_matter_channel(app_db_url, tid, "X", "Y")
        )
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/channels/{chan_id}/messages",
                json={"body": "should not land"},
                headers=_auth(),  # aetoes token, foreign channel
            )
        assert resp.status_code == 404

    def test_cross_tenant_document_reference_rejected(
        self, app_db_url: str, tmp_path
    ) -> None:
        tid = asyncio.run(_provision_tenant(app_db_url))
        foreign_doc = asyncio.run(_ingest_doc(app_db_url, tmp_path, tid))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/channels/{GENERAL_CHANNEL}/messages",
                json={"body": "see this", "document_id": str(foreign_doc)},
                headers=_auth(),
            )
        assert resp.status_code == 404
        assert "document" in resp.json()["detail"]

    def test_reply_thread_and_valid_document_reference(
        self, app_db_url: str, tmp_path
    ) -> None:
        doc_id = asyncio.run(_ingest_doc(app_db_url, tmp_path, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            top = client.post(
                f"/v1/channels/{GENERAL_CHANNEL}/messages",
                json={"body": "Opposing brief filed."},
                headers=_auth(),
            )
            assert top.status_code == 201
            reply = client.post(
                f"/v1/channels/{GENERAL_CHANNEL}/messages",
                json={
                    "body": "Running adversarial analysis now.",
                    "thread_id": top.json()["id"],
                    "document_id": str(doc_id),
                },
                headers=_auth(),
            )
        assert reply.status_code == 201

    def test_empty_body_rejected(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/channels/{GENERAL_CHANNEL}/messages",
                json={"body": ""},
                headers=_auth(),
            )
        assert resp.status_code == 422
