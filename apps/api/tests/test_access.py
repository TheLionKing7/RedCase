"""Access-request flow tests — IA spec §1.6 (S10-4)."""

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

from app.config import Settings
from app.main import create_app

JWT_SECRET = "test-access-secret"  # noqa: S105


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_jwt(*, sub="staff", tenant=SEED_TENANT_AETOES, clearance="STAFF"):
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "exp": int(time.time()) + 3600,
        "app_metadata": {"tenant_id": tenant, "clearance": clearance},
    }
    seg = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    sig = hmac.new(JWT_SECRET.encode(), seg.encode(), hashlib.sha256).digest()
    return f"{seg}.{_b64url(sig)}"


def _auth(**kw):
    return {"Authorization": f"Bearer {make_jwt(**kw)}"}


def _settings(app_db_url):
    return Settings(_env_file=None, database_url=app_db_url, supabase_jwt_secret=JWT_SECRET)


async def _provision_doc(app_db_url, tenant=SEED_TENANT_AETOES):
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            vault = await conn.fetchval(
                "SELECT id FROM vaults WHERE tenant_id = $1::uuid LIMIT 1", tenant
            )
            doc = uuid.uuid4()
            await conn.execute(
                "INSERT INTO documents"
                " (id, tenant_id, vault_id, case_title, citation, court_level, year,"
                "  source_pdf_path, pdf_sha256)"
                " VALUES ($1, $2, $3, $4, $5, 'FEDERAL_HIGH_COURT', 2024,"
                "  '/seed/a.pdf', 'decafbad')",
                doc, tenant, vault, f"AR doc {uuid.uuid4().hex[:6]}",
                f"[2026] FHC/{uuid.uuid4().hex[:6]}",
            )
        return doc
    finally:
        await conn.close()


async def _check_grant(app_db_url, doc, user_ref, tenant=SEED_TENANT_AETOES):
    conn = await asyncpg.connect(app_db_url)
    try:
        # document_grants RLS evaluates current_setting('app.tenant_id'); set the
        # GUC on this raw connection so the tenant_isolation policy resolves.
        # is_local=false → session-scoped, which works outside a transaction
        # (is_local=true is a no-op on a bare connection).
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", tenant)
        return await conn.fetchval(
            "SELECT count(*) FROM document_grants WHERE document_id = $1::uuid AND user_ref = $2",
            doc, user_ref,
        )
    finally:
        await conn.close()


class TestAccessRequestWorkflow:
    def test_request_then_partner_approves_writes_grant(self, app_db_url):
        doc = asyncio.run(_provision_doc(app_db_url))
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.post(
                "/v1/access-requests",
                json={"document_id": str(doc), "grantee_ref": "staff-b",
                     "grant_level": "READ", "reason": "review"},
                headers=_auth(sub="staff-a", clearance="STAFF"),
            )
            assert r.status_code == 201, r.text
            rid = r.json()["request"]["id"]
            assert r.json()["request"]["status"] == "PENDING"
            denied = client.post(
                f"/v1/access-requests/{rid}/decide",
                json={"approve": True},
                headers=_auth(sub="staff-a", clearance="STAFF"),
            )
            assert denied.status_code == 403
            ok = client.post(
                f"/v1/access-requests/{rid}/decide",
                json={"approve": True},
                headers=_auth(sub="partner", clearance="PARTNER"),
            )
            assert ok.status_code == 200, ok.text
            assert ok.json()["status"] == "APPROVED"
            assert asyncio.run(_check_grant(app_db_url, doc, "staff-b")) == 1

    def test_decider_cannot_self_approve(self, app_db_url):
        doc = asyncio.run(_provision_doc(app_db_url))
        with TestClient(create_app(_settings(app_db_url))) as client:
            # A staffer requests a grant FOR the partner; the partner (the decider)
            # is also the grantee, so they may not approve it themselves.
            r = client.post(
                "/v1/access-requests",
                json={"document_id": str(doc), "grantee_ref": "partner",
                     "grant_level": "READ"},
                headers=_auth(sub="staff-a", clearance="STAFF"),
            )
            assert r.status_code == 201, r.text
            rid = r.json()["request"]["id"]
            res = client.post(
                f"/v1/access-requests/{rid}/decide",
                json={"approve": True},
                headers=_auth(sub="partner", clearance="PARTNER"),
            )
            assert res.status_code == 403
            assert asyncio.run(_check_grant(app_db_url, doc, "partner")) == 0

    def test_deny_marks_request_and_writes_no_grant(self, app_db_url):
        doc = asyncio.run(_provision_doc(app_db_url))
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.post(
                "/v1/access-requests",
                json={"document_id": str(doc), "grantee_ref": "staff-b"},
                headers=_auth(sub="staff-a", clearance="STAFF"),
            )
            rid = r.json()["request"]["id"]
            res = client.post(
                f"/v1/access-requests/{rid}/decide",
                json={"approve": False},
                headers=_auth(sub="partner", clearance="PARTNER"),
            )
            assert res.status_code == 200
            assert res.json()["status"] == "DENIED"
            again = client.post(
                f"/v1/access-requests/{rid}/decide",
                json={"approve": True},
                headers=_auth(sub="partner2", clearance="PARTNER"),
            )
            assert again.status_code == 409
            assert asyncio.run(_check_grant(app_db_url, doc, "staff-b")) == 0

    def test_cross_tenant_isolated_empty(self, app_db_url):
        tenant_b = "b0000002-0000-4000-8000-000000000002"
        with TestClient(create_app(_settings(app_db_url))) as client:
            got = client.get(
                "/v1/access-requests",
                headers=_auth(sub="ghost", tenant=tenant_b, clearance="STAFF"),
            )
            assert got.status_code == 200
            assert got.json()["requests"] == []

