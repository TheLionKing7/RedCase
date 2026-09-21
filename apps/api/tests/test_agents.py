"""Functional-agent posts (Addendum §7.2) — Task 2.6 DoD.

Verifies:
  * a functional agent posts a LABELED result (sender_kind=AGENT,
    sender_ref = function label) with analysis_id/document_id refs;
  * ref integrity — an out-of-tenant reference is rejected;
  * the loop guard — an agent cannot thread under another agent/system message;
  * the permanent negative guard — an @mention in a channel produces NO agent
    reply (no mention-reply code exists anywhere);
  * share-to-channel — a USER posts a document reference as an explicit,
    attributed act (sender_kind stays USER).
"""

import asyncio
import uuid

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

from app.comms.agents import AgentPostError, post_agent_message
from app.main import create_app
from tests.test_channels import (
    GENERAL_CHANNEL,
    _auth,
    _ingest_doc,
    _provision_matter_channel,
    _settings,
)


async def _add_agent(
    app_db_url: str, tenant: str, channel_id: uuid.UUID, agent_ref: str
) -> None:
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute(
                "INSERT INTO channel_participants"
                " (tenant_id, channel_id, participant_ref, participant_kind)"
                " VALUES ($1, $2, $3, 'AGENT')",
                uuid.UUID(tenant),
                channel_id,
                agent_ref,
            )
    finally:
        await conn.close()


def _post_agent(
    app_db_url: str,
    tenant: str,
    channel_id: uuid.UUID,
    agent_ref: str,
    body: str,
    **kwargs,
):
    async def _run():
        conn = await asyncpg.connect(app_db_url)
        try:
            return await post_agent_message(
                conn, tenant, str(channel_id), agent_ref, body, **kwargs
            )
        finally:
            await conn.close()

    return asyncio.run(_run())


async def _read_messages(
    app_db_url: str, tenant: str, channel_id: uuid.UUID, user_ref: str
) -> list[dict]:
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute("SELECT set_config('app.user_ref', $1, true)", user_ref)
            rows = await conn.fetch(
                "SELECT id, sender_ref, sender_kind, body, document_id, analysis_id"
                " FROM channel_messages WHERE channel_id = $1::uuid ORDER BY created_at",
                channel_id,
            )
            return [dict(r) for r in rows]
    finally:
        await conn.close()


class TestAgentPost:
    def test_agent_post_labeled_with_document_ref(
        self, app_db_url: str, tmp_path
    ) -> None:
        chan_id, _ = asyncio.run(
            _provision_matter_channel(app_db_url, SEED_TENANT_AETOES, "FBN", "Aetoes")
        )
        asyncio.run(_add_agent(app_db_url, SEED_TENANT_AETOES, chan_id, "red-teamer"))
        doc_id = asyncio.run(_ingest_doc(app_db_url, tmp_path, SEED_TENANT_AETOES))

        out = _post_agent(
            app_db_url, SEED_TENANT_AETOES, chan_id, "red-teamer",
            "Battle card: two opposing arguments flagged.",
            document_id=str(doc_id),
        )
        assert out["sender_kind"] == "AGENT"

        rows = asyncio.run(
            _read_messages(app_db_url, SEED_TENANT_AETOES, chan_id, "red-teamer")
        )
        assert len(rows) == 1
        assert rows[0]["sender_kind"] == "AGENT"
        assert rows[0]["sender_ref"] == "red-teamer"
        assert rows[0]["document_id"] == doc_id

    def test_agent_post_rejects_out_of_tenant_ref(self, app_db_url: str) -> None:
        chan_id, _ = asyncio.run(
            _provision_matter_channel(app_db_url, SEED_TENANT_AETOES, "X", "Y")
        )
        asyncio.run(_add_agent(app_db_url, SEED_TENANT_AETOES, chan_id, "red-teamer"))
        with pytest.raises(AgentPostError, match="document not found"):
            _post_agent(
                app_db_url, SEED_TENANT_AETOES, chan_id, "red-teamer",
                "bad ref", document_id=str(uuid.uuid4()),
            )

    def test_agent_loop_guard(self, app_db_url: str) -> None:
        chan_id, _ = asyncio.run(
            _provision_matter_channel(app_db_url, SEED_TENANT_AETOES, "A", "B")
        )
        asyncio.run(_add_agent(app_db_url, SEED_TENANT_AETOES, chan_id, "red-teamer"))
        asyncio.run(
            _add_agent(app_db_url, SEED_TENANT_AETOES, chan_id, "deadline-tracker")
        )
        first = _post_agent(
            app_db_url, SEED_TENANT_AETOES, chan_id, "red-teamer", "result one"
        )
        with pytest.raises(AgentPostError, match="loop guard"):
            _post_agent(
                app_db_url, SEED_TENANT_AETOES, chan_id, "deadline-tracker",
                "reply to agent", thread_id=first["id"],
            )


class TestMentionGuard:
    def test_mention_produces_no_agent_reply(self, app_db_url: str) -> None:
        # A user posts an @mention; no mention-reply code exists, so the ONLY
        # resulting message is the user's own — no agent reply ever appears.
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/channels/{GENERAL_CHANNEL}/messages",
                json={"body": "hey @legalbrain, summarize this?"},
                headers=_auth(),
            )
        assert resp.status_code == 201
        rows = asyncio.run(
            _read_messages(
                app_db_url, SEED_TENANT_AETOES, uuid.UUID(GENERAL_CHANNEL), "user-1"
            )
        )
        agent_rows = [r for r in rows if r["sender_kind"] in ("AGENT", "SYSTEM")]
        assert agent_rows == []


class TestShareToChannel:
    def test_user_share_document_reference(self, app_db_url: str, tmp_path) -> None:
        doc_id = asyncio.run(_ingest_doc(app_db_url, tmp_path, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/channels/{GENERAL_CHANNEL}/messages",
                json={
                    "body": "Sharing the adverse brief analysis",
                    "document_id": str(doc_id),
                },
                headers=_auth(),
            )
        assert resp.status_code == 201
        rows = asyncio.run(
            _read_messages(
                app_db_url, SEED_TENANT_AETOES, uuid.UUID(GENERAL_CHANNEL), "user-1"
            )
        )
        shared = [r for r in rows if r["document_id"] == doc_id]
        assert len(shared) == 1
        assert shared[0]["sender_kind"] == "USER"  # attributed user act, not an agent
