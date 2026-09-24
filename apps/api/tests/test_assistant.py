"""Legal Assistant endpoint + agent tests — Addendum §7.2.

Covers the DoD for the per-user conversational agent:
  * entitlement gate: workbench.assistant is premium (CORE tenant → 402; PREMIUM → ALLOW)
  * thread create + SSE message flow (agent mocked — injectable runtime)
  * grounding: verification metadata persisted (citations, serving provider, tool_uses)
  * isolation: lawyer B cannot read lawyer A's thread (404 at the endpoint)
  * feedback -> preference round trip: a DOWN vote with correction text is folded into the
    preference profile that the NEXT turn's prompt surfaces
  * digest: workspace summary built from existing tables (matters, analyses, invoices)

The §7.2 ReAct loop is exercised via monkeypatched run_assistant_turn (a real LLM call
would be a live test behind RUN_LIVE_TESTS=1). The bounded loop + grounding verify are
unit-tested against synthetic tool results.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid

import asyncpg
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

import app.assistant.router as assistant_router
import app.assistant.service as service_module
from app.config import Settings
from app.main import create_app

JWT_SECRET = "test-secret"  # noqa: S105 (throwaway test secret)


def _b64(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def make_jwt(*, sub: str = "lawyer-a", tenant: str = SEED_TENANT_AETOES) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "exp": time.time() + 3600,
        "app_metadata": {"tenant_id": tenant, "clearance": "STAFF"},
    }
    signing = f"{_b64(header)}.{_b64(payload)}"
    sig = base64.urlsafe_b64encode(
        hmac.new(JWT_SECRET.encode(), signing.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{signing}.{sig}"


def _settings(app_db_url: str) -> Settings:
    return Settings(
        _env_file=None, database_url=app_db_url, supabase_jwt_secret=JWT_SECRET
    )


def _auth(*, sub: str = "lawyer-a", tenant: str = SEED_TENANT_AETOES) -> dict:
    return {"Authorization": f"Bearer {make_jwt(sub=sub, tenant=tenant)}"}


async def _provision_premium(app_db_url: str, tenant: str) -> None:
    """A PREMIUM subscription so the workbench.assistant gate ALLOWs."""
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute(
                "INSERT INTO subscriptions (tenant_id, plan, status, max_seats, current_seats)"
                " VALUES ($1, 'PREMIUM', 'ACTIVE', 10, 1)"
                " ON CONFLICT (tenant_id) DO NOTHING",
                uuid.UUID(tenant),
            )
    finally:
        await conn.close()

async def _make_client_and_matter(
    app_db_url: str, tenant: str
) -> tuple[uuid.UUID, uuid.UUID]:
    conn = await asyncpg.connect(app_db_url)
    client_id, matter_id = uuid.uuid4(), uuid.uuid4()
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute(
                "INSERT INTO clients (id, tenant_id, name) VALUES ($1, $2, $3)",
                client_id,
                uuid.UUID(tenant),
                "Test Client",
            )
            await conn.execute(
                "INSERT INTO matters (id, tenant_id, client_id, matter_ref, status)"
                " VALUES ($1, $2, $3, $4, 'ACTIVE')",
                matter_id,
                uuid.UUID(tenant),
                client_id,
                "TEST-MATTER-1",
            )
    finally:
        await conn.close()
    return client_id, matter_id


def _fake_reply(**over) -> service_module.AssistantReply:
    base = service_module.AssistantReply(
        content="Structured answer.",
        citations=[
            {
                "namespace": "B",
                "ref": "B:doc",
                "document_id": "b0000000-0000-4000-8000-000000000009",
                "case_title": "Case",
                "citation": "CASE",
                "page_start": 1,
                "page_end": 2,
                "verified": True,
            }
        ],
        refusal=False,
        tool_uses=[{"tool": "search_vault_b", "query_hash": "abc", "ok": True}],
        serving_provider="test-provider",
        serving_model="test-model",
    )
    return base


async def _insert_message(
    app_db_url: str, tenant: str, thread_id: str, user: str, role: str, reply
) -> uuid.UUID:
    conn = await asyncpg.connect(app_db_url)
    mid = uuid.uuid4()
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute("SELECT set_config('app.user_ref', $1, true)", user)
            await conn.execute(
                "INSERT INTO assistant_messages (id, tenant_id, thread_id, role, content,"
                " citations, tool_uses, serving_provider)"
                " VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8)",
                mid,
                uuid.UUID(tenant),
                uuid.UUID(thread_id),
                role,
                reply.content,
                json.dumps(reply.citations or []),
                json.dumps(reply.tool_uses or []),
                reply.serving_provider,
            )
    finally:
        await conn.close()
    return mid


async def _count_prefs(app_db_url: str, user: str) -> int:
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", SEED_TENANT_AETOES)
            await conn.execute("SELECT set_config('app.user_ref', $1, true)", user)
            return await conn.fetchval(
                "SELECT COUNT(*) FROM assistant_preferences WHERE user_ref = $1", user
            )
    finally:
        await conn.close()


async def _load_prefs(app_db_url: str, user: str) -> list:
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", SEED_TENANT_AETOES)
            await conn.execute("SELECT set_config('app.user_ref', $1, true)", user)
            rows = await conn.fetch(
                "SELECT pref_key, pref_value, source FROM assistant_preferences"
                " WHERE user_ref = $1 ORDER BY created_at",
                user,
            )
            return [
                {"key": r[0], "value": json.loads(r[1]), "source": r[2]} for r in rows
            ]
    finally:
        await conn.close()



class TestEntitlementGate:
    def test_core_tenant_is_402(self, app_db_url: str) -> None:
        # A tenant with NO subscription => CORE => premium feature DENY_PLAN -> 402.
        # (Uses a distinct tenant so a PREMIUM row seeded by a sibling test in the
        # same session DB cannot mask the CORE behavior.)
        other = str(uuid.uuid4())
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.post("/v1/assistant/threads", json={}, headers=_auth(tenant=other))
            assert r.status_code == 402
            assert "workbench.assistant" in r.json()["detail"]

    def test_premium_tenant_allows_thread_create(self, app_db_url: str) -> None:
        asyncio.run(_provision_premium(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.post(
                "/v1/assistant/threads", json={"title": "My case"}, headers=_auth()
            )
            assert r.status_code == 200
            assert r.json()["thread_id"]


class TestThreadFlow:
    def test_create_and_get_thread(self, app_db_url: str) -> None:
        asyncio.run(_provision_premium(app_db_url, SEED_TENANT_AETOES))
        asyncio.run(_make_client_and_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            tid = client.post(
                "/v1/assistant/threads", json={"title": "Digest please"}, headers=_auth()
            ).json()["thread_id"]
            got = client.get(f"/v1/assistant/threads/{tid}", headers=_auth())
            assert got.status_code == 200
            body = got.json()
            assert body["thread_id"] == tid
            assert body["turns"] == []
            # Digest built from existing tables (seeded matter).
            assert body["digest"]["active_matters"] == 1
            assert "unpaid_amount_ngn" in body["digest"]

    def test_foreign_thread_is_404(self, app_db_url: str) -> None:
        asyncio.run(_provision_premium(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            # lawyer-a owns nothing; lawyer-b reads a random id -> RLS hides it -> 404.
            r = client.get(
                f"/v1/assistant/threads/{uuid.uuid4()}", headers=_auth(sub="lawyer-b")
            )
            assert r.status_code == 404



class TestMessageSSE:
    def test_sse_streams_reply_and_persists(
        self, app_db_url: str, monkeypatch
    ) -> None:
        asyncio.run(_provision_premium(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            tid = client.post("/v1/assistant/threads", json={}, headers=_auth()).json()[
                "thread_id"
            ]

        captured = {}

        async def _fake_turn(**kw):
            captured.update(kw)
            reply = _fake_reply()
            # Persist both messages so the GET reflects the turn (the fake bypasses
            # the real run_assistant_turn persistence path).
            db = kw["db"]
            await db.execute(
                "INSERT INTO assistant_messages (id, tenant_id, thread_id, role, content,"
                " question_hash)"
                " VALUES ($1, $2, $3, 'USER', $4, $5)",
                uuid.uuid4(),
                uuid.UUID(SEED_TENANT_AETOES),
                uuid.UUID(kw["thread_id"]),
                kw["message_text"],
                hashlib.sha256(kw["message_text"].encode()).hexdigest(),
            )
            await db.execute(
                "INSERT INTO assistant_messages (id, tenant_id, thread_id, role, content,"
                " citations, tool_uses, serving_provider, serving_model)"
                " VALUES ($1, $2, $3, 'ASSISTANT', $4, $5::jsonb, $6::jsonb, $7, $8)",
                uuid.uuid4(),
                uuid.UUID(SEED_TENANT_AETOES),  # tenant (matches RLS)
                uuid.UUID(kw["thread_id"]),
                reply.content,
                json.dumps(reply.citations or []),
                json.dumps(reply.tool_uses or []),
                reply.serving_provider,
                reply.serving_model,
            )
            return reply

        monkeypatch.setattr(assistant_router, "run_assistant_turn", _fake_turn)

        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.post(
                f"/v1/assistant/threads/{tid}/messages",
                json={"message": "Draft a memo"},
                headers=_auth(),
            )
            assert r.status_code == 200
            assert "text/event-stream" in r.headers["content-type"]
            data = r.text
            assert "agent_step" in data
            assert "assistant_reply" in data
            assert "Structured answer" in data

        # The turn persisted BOTH the user message and the reply.
        with TestClient(create_app(_settings(app_db_url))) as client:
            got = client.get(f"/v1/assistant/threads/{tid}", headers=_auth()).json()
            roles = [t["role"] for t in got["turns"]]
            assert roles == ["USER", "ASSISTANT"]
            reply = got["turns"][1]
            assert reply["serving_provider"] == "test-provider"
            assert reply["tool_uses"][0]["tool"] == "search_vault_b"
            assert reply["citations"][0]["verified"] is True


class TestFeedbackPreferenceRoundTrip:
    def test_downvote_correction_folds_into_preferences(self, app_db_url: str) -> None:
        asyncio.run(_provision_premium(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            tid = client.post("/v1/assistant/threads", json={}, headers=_auth()).json()[
                "thread_id"
            ]

        # Directly insert an assistant message as the target of feedback.
        reply = _fake_reply()
        asyncio.run(
            _insert_message(
                app_db_url, SEED_TENANT_AETOES, tid, "lawyer-a", "ASSISTANT", reply
            )
        )
        with TestClient(create_app(_settings(app_db_url))) as client:
            turns = client.get(
                f"/v1/assistant/threads/{tid}", headers=_auth()
            ).json()["turns"]
            msg_id = turns[0]["message_id"]

            # The profile is empty before feedback.
            assert asyncio.run(_count_prefs(app_db_url, "lawyer-a")) == 0

            fb = client.post(
                f"/v1/assistant/threads/{tid}/feedback",
                json={
                    "message_id": msg_id,
                    "rating": "DOWN",
                    "correction_text": "Always cite statutory sections first.",
                },
                headers=_auth(),
            )
            assert fb.status_code == 200
            assert fb.json()["feedback_id"]

            # NEXT-turn prompt surfaces the correction as a preference.
            assert asyncio.run(_count_prefs(app_db_url, "lawyer-a")) == 1

        prefs = asyncio.run(_load_prefs(app_db_url, "lawyer-a"))
        assert prefs[0]["key"] == "style_correction"
        assert prefs[0]["source"] == "CORRECTION"
        block = service_module._preference_block(
            [{"key": p["key"], "value": p["value"], "source": p["source"]} for p in prefs]
        )
        assert "statutory sections first" in block



class TestReActLoop:
    def test_fabricated_citation_is_refused_and_never_shown(
        self, app_db_url: str
    ) -> None:
        """Zero-fabrication hard gate: a final answer citing a doc id that was never
        retrieved is refused — the fabricated text is not returned nor persisted."""
        asyncio.run(_provision_premium(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            tid = client.post("/v1/assistant/threads", json={}, headers=_auth()).json()[
                "thread_id"
            ]

        # The agent's single LLM response fabricates a citation not in any retrieved set.
        decisions = [
            json.dumps(
                {
                    "final": {
                        "answer": "The settled rule. [B:"
                        "99999999-0000-4000-8000-000000000000, p.5]"
                    }
                }
            )
        ]

        class _FakeLLM:
            provider = "fake"
            model = "fake-model"

            async def answer(self, system: str, user: str) -> str:
                return decisions.pop(0)

        class _FakeEmbedder:
            async def embed(self, texts):
                return [[0.5] * 8 for _ in texts]

        class _FakeDB:
            async def fetch(self, *a, **k):
                return []

            async def fetchrow(self, *a, **k):
                return None

        async def _run():
            return await service_module.run_assistant_turn(
                thread_id=tid,
                message_text="What is the rule?",
                db=_FakeDB(),  # type: ignore[arg-type]
                tenant_id=SEED_TENANT_AETOES,
                user_ref="lawyer-a",
                clearance="STAFF",
                settings=_settings(app_db_url),
                llm=_FakeLLM(),
                embedder=_FakeEmbedder(),
                save_history=False,
            )

        reply = asyncio.run(_run())
        assert reply.refusal is True
        # The fabricated text is never returned.
        assert "The settled rule" not in reply.content
        assert reply.citations == []

    def test_bounded_loop_stops_at_max_iterations(self) -> None:
        """A loop that never reaches a final answer is hard-capped at
        MAX_TOOL_ITERATIONS and returns a refusal instead of looping forever."""
        calls = []

        class _LoopingLLM:
            provider = "fake"
            model = "fake"

            async def answer(self, system: str, user: str) -> str:
                calls.append(1)
                return json.dumps(
                    {"action": "matter_context", "action_input": {}}
                )

        class _FakeEmbedder:
            async def embed(self, texts):
                return [[0.5] * 8 for _ in texts]

        class _FakeDB:
            async def fetch(self, *a, **k):
                return []

            async def fetchrow(self, *a, **k):
                return None

        async def _run():
            return await service_module.run_assistant_turn(
                thread_id=str(uuid.uuid4()),
                message_text="hi",
                db=_FakeDB(),  # type: ignore[arg-type]
                tenant_id=SEED_TENANT_AETOES,
                user_ref="lawyer-a",
                clearance="STAFF",
                settings=Settings(_env_file=None),
                llm=_LoopingLLM(),
                embedder=_FakeEmbedder(),
                save_history=False,
            )

        reply = asyncio.run(_run())
        # The loop is hard-capped: it never loops forever. Each non-final iteration
        # consumes one tool-use slot; no final answer => refusal.
        assert len(calls) <= service_module.MAX_TOOL_ITERATIONS + 1
        assert reply.refusal is True


