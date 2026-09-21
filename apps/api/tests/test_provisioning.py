"""Provisioning polish (Addendum §7.3) — Task 2.7 DoD.

Verifies:
  * DIRECT channel creation (POST /v1/channels) — idempotent, both participants;
  * the transparency feed (GET /v1/audit) matches query_audit (parity) and is
    redacted (metadata only, no answer_text/citations/question bodies);
  * the channel-shared intake ruling: a CONFIDENTIAL document shared in a
    channel stays readable ONLY by its grant-holders (uploader + named
    individuals) — channel membership never widens the document ACL.
"""

import asyncio
import uuid

import asyncpg
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.vault_a.crypto import make_key_provider
from app.vault_a.ingest import intake_document
from tests.pdf_factory import make_pdf, synthetic_judgment_pages
from tests.test_channels import (
    _auth,
    _auth_sub,
    _settings,
)
from tests.test_vault_a_ingest import MASTER_KEY_HEX, ConstantEmbedder

JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105


async def _insert_audit(app_db_url: str, tenant: str, question_hash: str) -> None:
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute(
                "INSERT INTO query_audit"
                " (id, tenant_id, user_ref, question_hash, threshold_passed, latency_ms)"
                " VALUES ($1, $2, 'user-1', $3, FALSE, 123)",
                uuid.uuid4(),
                uuid.UUID(tenant),
                question_hash,
            )
    finally:
        await conn.close()


async def _ingest_confidential(
    app_db_url: str, tenant: str, uploader: str, tmp_path
) -> tuple[uuid.UUID, uuid.UUID]:
    """Firm vault + client + matter + a CONFIDENTIAL doc granted only to uploader."""
    conn = await asyncpg.connect(app_db_url)
    vault_id, client_id, matter_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute("SELECT set_config('app.user_ref', $1, true)", uploader)
            await conn.execute("SELECT set_config('app.user_clearance', 'PARTNER', true)")
            await conn.execute(
                "INSERT INTO vaults (id, tenant_id, vault_type, name) VALUES ($1, $2, 'firm', 'V')",
                vault_id,
                tenant,
            )
            await conn.execute(
                "INSERT INTO clients (id, tenant_id, name) VALUES ($1, $2, 'Client')",
                client_id,
                tenant,
            )
            await conn.execute(
                "INSERT INTO matters (id, tenant_id, client_id, matter_ref)"
                " VALUES ($1, $2, $3, 'M v. S')",
                matter_id,
                tenant,
                client_id,
            )
    finally:
        await conn.close()

    pages = synthetic_judgment_pages()
    pdf = make_pdf(tmp_path / f"conf-{uuid.uuid4().hex[:8]}.pdf", pages)
    settings = Settings(
        database_url=app_db_url,
        vault_a_key_provider="local",
        vault_a_master_key=MASTER_KEY_HEX,
    )
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute("SELECT set_config('app.user_ref', $1, true)", uploader)
            await conn.execute("SELECT set_config('app.user_clearance', 'PARTNER', true)")
            result = await intake_document(
                conn=conn,
                settings=settings,
                provider=make_key_provider(settings),
                embedder=ConstantEmbedder(),
                tenant_id=tenant,
                uploader=uploader,
                uploader_clearance="PARTNER",
                matter_id=matter_id,
                raw=pdf.read_bytes(),
                filename="conf.pdf",
                classification="CONFIDENTIAL",
                doc_type="BRIEF",
                grantees=[],
            )
        return matter_id, uuid.UUID(result["document_id"])
    finally:
        await conn.close()


async def _count_docs_as(
    app_db_url: str, tenant: str, user_ref: str, clearance: str, doc_id: uuid.UUID
) -> int:
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute("SELECT set_config('app.user_ref', $1, true)", user_ref)
            await conn.execute("SELECT set_config('app.user_clearance', $1, true)", clearance)
            return await conn.fetchval(
                "SELECT count(*) FROM documents WHERE id = $1::uuid", doc_id
            )
    finally:
        await conn.close()


class TestDirectChannel:
    def test_create_direct_channel_idempotent(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/channels",
                json={"kind": "DIRECT", "other_user_ref": "user-b"},
                headers=_auth_sub("user-a"),
            )
        assert resp.status_code == 201
        chan_id = resp.json()["id"]

        with TestClient(create_app(_settings(app_db_url))) as client:
            again = client.post(
                "/v1/channels",
                json={"kind": "DIRECT", "other_user_ref": "user-b"},
                headers=_auth_sub("user-a"),
            )
        assert again.status_code == 201
        assert again.json()["id"] == chan_id  # order-independent, idempotent

    def test_create_channel_rejects_non_direct(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/channels",
                json={"kind": "MATTER", "other_user_ref": "user-b"},
                headers=_auth_sub("user-a"),
            )
        assert resp.status_code == 400


class TestTransparencyFeed:
    def test_audit_feed_parity(self, app_db_url: str) -> None:
        qh = f"feed-{uuid.uuid4().hex}"
        asyncio.run(_insert_audit(app_db_url, SEED_TENANT_AETOES, qh))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.get("/v1/audit", headers=_auth())
        assert resp.status_code == 200
        hashes = [e["question_hash"] for e in resp.json()["entries"]]
        assert qh in hashes
        # Redacted: the feed carries metadata only.
        for entry in resp.json()["entries"]:
            assert "answer_text" not in entry
            assert "citations" not in entry


class TestChannelSharedIntake:
    def test_confidential_doc_shared_not_leaked_to_participant(
        self, app_db_url: str, tmp_path
    ) -> None:
        matter_id, doc_id = asyncio.run(
            _ingest_confidential(app_db_url, SEED_TENANT_AETOES, "uploader-a", tmp_path)
        )
        # A channel with uploader-a and a non-granted STAFF participant.
        with TestClient(create_app(_settings(app_db_url))) as client:
            chan = client.post(
                "/v1/channels",
                json={"kind": "DIRECT", "other_user_ref": "staff-b"},
                headers=_auth_sub("uploader-a"),
            )
        chan_id = uuid.UUID(chan.json()["id"])

        # uploader-a shares the doc in the channel (explicit, attributed act).
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/channels/{chan_id}/messages",
                json={"body": "Sharing the brief", "document_id": str(doc_id)},
                headers=_auth_sub("uploader-a"),
            )
        assert resp.status_code == 201

        # The non-granted STAFF participant reads ZERO documents (RLS, not
        # channel membership, is the door).
        assert (
            asyncio.run(
                _count_docs_as(
                    app_db_url, SEED_TENANT_AETOES, "staff-b", "STAFF", doc_id
                )
            )
            == 0
        )
        # The uploader (grant-holder) still reads it.
        assert (
            asyncio.run(
                _count_docs_as(
                    app_db_url, SEED_TENANT_AETOES, "uploader-a", "PARTNER", doc_id
                )
            )
            == 1
        )

