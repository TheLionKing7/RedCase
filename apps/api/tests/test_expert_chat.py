"""Expert Chat endpoint tests (Addendum §3.2 Step D) — the Legal Assistant.

The grounding contract (answer_question) is already covered by test_retrieval;
here we verify the chat-specific surface: per-user thread management, the
thread_id/analysis_id hand-off, and the 404 for a foreign analysis.
"""

import asyncio
import uuid

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

import app.routers.expert_chat as expert_chat_module
from app.config import Settings
from app.main import create_app
from tests.test_query_api import make_jwt

JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105
VAULT_JURIS_NG = uuid.UUID("b0000001-0000-4000-8000-000000000001")


def _settings(app_db_url: str) -> Settings:
    return Settings(
        _env_file=None, database_url=app_db_url, supabase_jwt_secret=JWT_SECRET
    )


def _auth(sub: str = "user-1", tenant: str = SEED_TENANT_AETOES) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_jwt(sub=sub, tenant=tenant)}"}


async def _create_analysis(
    app_db_url: str, tenant: str, created_by: str
) -> tuple[uuid.UUID, uuid.UUID]:
    conn = await asyncpg.connect(app_db_url)
    doc_id, analysis_id = uuid.uuid4(), uuid.uuid4()
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute(
                "INSERT INTO documents (id, tenant_id, vault_id, case_title,"
                " citation, court_level, year, source_pdf_path, pdf_sha256)"
                " VALUES ($1, $2, $3, 'Chat Case', $4, 'SUPREME_COURT', 2000,"
                " 's3://x.pdf', $5)",
                doc_id,
                tenant,
                VAULT_JURIS_NG,
                f"CHAT-{uuid.uuid4().hex[:12]}",  # unique citation per test
                uuid.uuid4().hex + uuid.uuid4().hex,
            )
            await conn.execute(
                "INSERT INTO document_analyses (id, tenant_id, document_id,"
                " prompt_pack, status, created_by)"
                " VALUES ($1, $2, $3, 'ADVERSARIAL_BRIEF', 'COMPLETE', $4)",
                analysis_id,
                tenant,
                doc_id,
                created_by,
            )
        return doc_id, analysis_id
    finally:
        await conn.close()


class TestExpertChat:
    def test_chat_creates_thread_and_returns_answer(
        self, app_db_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, analysis_id = asyncio.run(
            _create_analysis(app_db_url, SEED_TENANT_AETOES, "user-1")
        )

        captured: dict = {}

        async def _fake_answer(question, filters, db, tenant_id, user_ref, **kw):
            captured.update(kw)
            return {
                "answer": "No binding precedent found in Vault B.",
                "citations": [],
                "refusal": True,
            }

        monkeypatch.setattr(expert_chat_module, "answer_question", _fake_answer)

        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/analyses/{analysis_id}/chat",
                json={"question": "What is the weakness in paragraph 3?"},
                headers=_auth(),
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["refusal"] is True
        assert body["thread_id"]  # a thread was created

        # The grounding call received the thread + analysis scoping.
        assert captured["thread_id"] == body["thread_id"]
        assert captured["analysis_id"] == str(analysis_id)

    def test_chat_returns_404_for_foreign_analysis(
        self, app_db_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _, analysis_id = asyncio.run(
            _create_analysis(app_db_url, SEED_TENANT_AETOES, "someone-else")
        )
        # user-1 did not create this analysis -> per-user workbench 404.
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/analyses/{analysis_id}/chat",
                json={"question": "hi"},
                headers=_auth(),
            )
        assert resp.status_code == 404
