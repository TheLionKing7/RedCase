import asyncio
import json
import uuid

import asyncpg
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

import app.assistant.service as svc
from app.config import Settings
from app.main import create_app
from app.retrieval.prompts import GROUNDED_SYSTEM
from app.retrieval.service import HYBRID_SQL

JWT_SECRET = "test-secret"
FIRM_DEFAULTS = ["Tax", "Litigation"]


def make_jwt(*, sub="lawyer-a", tenant=SEED_TENANT_AETOES, is_admin=False):
    import base64
    import hashlib
    import hmac
    import time
    def _b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    meta = {"tenant_id": tenant, "clearance": "ADMIN" if is_admin else "STAFF"}
    if is_admin:
        meta["is_firm_admin"] = True
    header, payload = {"alg": "HS256", "typ": "JWT"}, {"sub": sub, "exp": time.time() + 3600, "app_metadata": meta}
    signing = f"{_b64(header)}.{_b64(payload)}"
    sig = base64.urlsafe_b64encode(hmac.new(JWT_SECRET.encode(), signing.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    return f"{signing}.{sig}"


def _settings(app_db_url):
    return Settings(_env_file=None, database_url=app_db_url, supabase_jwt_secret=JWT_SECRET)


def _auth(*, sub="lawyer-a", tenant=SEED_TENANT_AETOES, is_admin=False):
    return {"Authorization": f"Bearer {make_jwt(sub=sub, tenant=tenant, is_admin=is_admin)}"}


async def _ensure_tenant(app_db_url, tenant):
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("INSERT INTO tenants (id, name, slug) VALUES ($1, " + "'Test LLP', $2) ON CONFLICT (id) DO NOTHING", uuid.UUID(tenant), f"t-{tenant[:8]}")
    finally:
        await conn.close()
    

class TestPersonaPersistence:
    def test_upsert_and_read_own_persona(self, app_db_url):
        asyncio.run(_ensure_tenant(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.put(
                "/v1/persona",
                json={"agent_name": "Amara", "rules_of_engagement": "Always cite the ratio and flag doubt.",
                     "tone_preset": "CONCISE", "practice_areas": ["Tax", "Corporate"]},
                headers=_auth(),
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["agent_name"] == "Amara"
            assert body["tone_preset"] == "CONCISE"
            assert body["practice_areas"] == ["Tax", "Corporate"]
            got = client.get("/v1/persona", headers=_auth()).json()
            assert got["agent_name"] == "Amara"
            assert "ratio and flag doubt" in got["rules_of_engagement"]

    def test_upsert_is_idempotent_single_row(self, app_db_url):
        asyncio.run(_ensure_tenant(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            for _ in range(2):
                client.put("/v1/persona", json={"agent_name": "Amara", "tone_preset": "NARRATIVE", "practice_areas": ["Litigation"]}, headers=_auth())
            assert client.get("/v1/persona", headers=_auth()).json()["tone_preset"] == "NARRATIVE"

    def test_invalid_tone_rejected(self, app_db_url):
        asyncio.run(_ensure_tenant(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.put("/v1/persona", json={"tone_preset": "SHOUTY"}, headers=_auth())
            assert r.status_code == 422
    

class TestPersonaRlsIsolation:
    def test_lawyer_b_cannot_read_lawyer_a_persona(self, app_db_url):
        asyncio.run(_ensure_tenant(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            client.put("/v1/persona", json={"agent_name": "Amara", "rules_of_engagement": "SECRET-RULES", "tone_preset": "FORMAL", "practice_areas": ["Tax"]}, headers=_auth(sub="lawyer-a"))
            got = client.get("/v1/persona", headers=_auth(sub="lawyer-b")).json()
            assert got["agent_name"] == "Assistant"
            assert "SECRET-RULES" not in json.dumps(got)

    def test_lawyer_b_updates_only_own_row(self, app_db_url):
        asyncio.run(_ensure_tenant(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            client.put("/v1/persona", json={"agent_name": "Amara", "tone_preset": "FORMAL"}, headers=_auth(sub="lawyer-a"))
            client.put("/v1/persona", json={"agent_name": "Bola", "tone_preset": "CONCISE"}, headers=_auth(sub="lawyer-b"))
            assert client.get("/v1/persona", headers=_auth(sub="lawyer-a")).json()["agent_name"] == "Amara"
            assert client.get("/v1/persona", headers=_auth(sub="lawyer-b")).json()["agent_name"] == "Bola"


class TestPracticeAreasLens:
    def test_firm_defaults_and_persona_override(self, app_db_url):
        asyncio.run(_ensure_tenant(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            admin = client.put("/v1/persona/practice-areas", json={"tags": FIRM_DEFAULTS}, headers=_auth(sub="lawyer-a", is_admin=True))
            assert admin.status_code == 200, admin.text
            got = client.get("/v1/persona/practice-areas", headers=_auth(sub="lawyer-b")).json()["tags"]
            assert sorted(got) == sorted(FIRM_DEFAULTS)
            denied = client.put("/v1/persona/practice-areas", json={"tags": ["X"]}, headers=_auth(sub="lawyer-b"))
            assert denied.status_code == 403

    def test_grounding_contract_survives_persona_injection(self):
        assert "Use ONLY the <passages> provided" in GROUNDED_SYSTEM
        assert "Never invent case names" in GROUNDED_SYSTEM
        assert "persona" in svc.AGENT_SYSTEM

    def test_retrieval_sql_has_legal_topics_prefilter(self):
        assert "d.legal_topics && $10" in HYBRID_SQL
        assert HYBRID_SQL.count("d.legal_topics && $10") == 2


class TestPersonaBlock:
    def test_persona_block_format(self):
        block = svc._persona_block({"agent_name": "Amara", "tone_preset": "CONCISE", "rules_of_engagement": "Be brief.", "practice_areas": ["Tax"]})
        assert "Amara" in block
        assert "CONCISE" in block
        assert "Practice-area lens: Tax" in block

    def test_persona_block_default(self):
        assert "Default assistant" in svc._persona_block({})

    def test_persona_tones_constant(self):
        assert svc.PERSONA_TONES == ("PROFESSIONAL", "CONCISE", "NARRATIVE", "FORMAL")
    


class TestDepartmentsModules:
    def test_firm_admin_replaces_departments_and_keeps_legal_practice(self, app_db_url):
        asyncio.run(_ensure_tenant(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            saved = client.put(
                "/v1/persona/departments",
                json={"departments": ["Operations", "Operations", ""]},
                headers=_auth(sub="lawyer-a", is_admin=True),
            )
            assert saved.status_code == 200, saved.text
            assert saved.json()["departments"] == ["Legal Practice", "Operations"]
            got = client.get(
                "/v1/persona/departments", headers=_auth(sub="lawyer-b")
            )
            assert got.status_code == 200
            assert got.json()["departments"] == ["Legal Practice", "Operations"]

    def test_non_admin_cannot_change_departments(self, app_db_url):
        asyncio.run(_ensure_tenant(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            denied = client.put(
                "/v1/persona/departments",
                json={"departments": ["Operations"]},
                headers=_auth(sub="lawyer-b"),
            )
            assert denied.status_code == 403

    def test_departments_are_tenant_scoped(self, app_db_url):
        other_tenant = str(uuid.uuid4())
        asyncio.run(_ensure_tenant(app_db_url, SEED_TENANT_AETOES))
        asyncio.run(_ensure_tenant(app_db_url, other_tenant))
        with TestClient(create_app(_settings(app_db_url))) as client:
            client.put(
                "/v1/persona/departments",
                json={"departments": ["Operations"]},
                headers=_auth(sub="lawyer-a", tenant=SEED_TENANT_AETOES, is_admin=True),
            )
            got = client.get(
                "/v1/persona/departments",
                headers=_auth(sub="lawyer-a", tenant=other_tenant),
            )
            assert got.status_code == 200
            assert got.json()["departments"] == []

