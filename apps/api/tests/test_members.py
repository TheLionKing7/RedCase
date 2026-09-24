"""Firm members (personnel identity) tests — IA §2 / migration 0024 (S10-4).

DoD under test: GET /v1/members/me returns the caller's REAL personnel name,
role + firm name from the register (never a clearance-only swing); a user with no
firm_members row -> 404; tenant isolation holds (a tenant B member sees only their
own firm, and a user in NO tenant's register still 404s for their tenant).
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time

import asyncpg
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105
TENANT_B = "b0000002-0000-4000-8000-000000000002"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_jwt(
    *,
    sub: str,
    tenant: str = SEED_TENANT_AETOES,
    clearance: str = "PARTNER",
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "exp": int(time.time()) + 3600,
        "app_metadata": {"tenant_id": tenant, "clearance": clearance},
    }
    seg = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    sig = hmac.new(JWT_SECRET.encode(), seg.encode(), hashlib.sha256).digest()
    return f"{seg}.{_b64url(sig)}"


def _auth(**kwargs) -> dict:
    return {"Authorization": f"Bearer {make_jwt(**kwargs)}"}


def _settings(app_db_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=app_db_url,
        supabase_jwt_secret=JWT_SECRET,
    )


async def _members(app_db_url: str, full_name: str, tenant: str, user_ref: str):
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute(
                "INSERT INTO tenants (id, name, slug, jurisdiction)"
                " VALUES ($1::uuid, $2, $2, 'NG') ON CONFLICT (id) DO NOTHING",
                tenant, f"Firm {tenant[:8]}",
            )
            await conn.execute(
                "INSERT INTO firm_members (tenant_id, user_ref, full_name, role, clearance)"
                " VALUES ($1::uuid, $2, $3, $4, $5)"
                " ON CONFLICT (tenant_id, user_ref) DO UPDATE SET full_name = EXCLUDED.full_name",
                tenant, user_ref, full_name, "Associate", "STAFF",
            )
    finally:
        await conn.close()


class TestDirectory:
    def test_directory_is_tenant_scoped_and_sorted(self, app_db_url):
        asyncio.run(_members(app_db_url, "Zara B", SEED_TENANT_AETOES, "directory-zara"))
        asyncio.run(_members(app_db_url, "Amina A", SEED_TENANT_AETOES, "directory-amina"))
        asyncio.run(_members(app_db_url, "Other Firm", TENANT_B, "directory-other"))
        with TestClient(create_app(_settings(app_db_url))) as client:
            response = client.get("/v1/members", headers=_auth(sub="directory-amina"))
        assert response.status_code == 200, response.text
        body = response.json()
        assert [member["full_name"] for member in body] == ["Amina A", "Tosin Adebayo", "Zara B"]
        assert all(member["full_name"] != "Other Firm" for member in body)


class TestMyMembership:
    def test_return_personnel_identity_and_firm_name(self, app_db_url):
        # The managing partner is seeded in migration 0024 for tenant zero.
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.get("/v1/members/me", headers=_auth(sub="mp-aetoes", clearance="PARTNER"))
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["full_name"] == "Tosin Adebayo"
            assert body["role"] == "Managing Partner"
            assert body["clearance"] == "PARTNER"
            assert isinstance(body["firm_name"], str) and body["firm_name"]

    def test_associate_member_returns_their_row(self, app_db_url):
        asyncio.run(
            _members(app_db_url, "Amina Yusuf", SEED_TENANT_AETOES, "assoc-1")
        )
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.get(
                "/v1/members/me",
                headers=_auth(sub="assoc-1", clearance="STAFF"),
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["full_name"] == "Amina Yusuf"
            assert body["role"] == "Associate"
            assert body["clearance"] == "STAFF"

    def test_no_register_row_returns_404(self, app_db_url):
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.get(
                "/v1/members/me",
                headers=_auth(sub="not-provisioned", clearance="STAFF"),
            )
            assert r.status_code == 404

    def test_cross_tenant_member_isolated(self, app_db_url):
        # amina is in tenant B only; asked as tenant B's same user_ref it resolves.
        asyncio.run(_members(app_db_url, "Amina B", TENANT_B, "amina"))
        with TestClient(create_app(_settings(app_db_url))) as client:
            ok = client.get("/v1/members/me", headers=_auth(sub="amina", tenant=TENANT_B))
            assert ok.status_code == 200, ok.text
            assert ok.json()["full_name"] == "Amina B"
            # Same user_ref in tenant A (no row) -> 404; RLS never leaks B's name.
            missing = client.get(
                "/v1/members/me", headers=_auth(sub="amina", tenant=SEED_TENANT_AETOES)
            )
            assert missing.status_code == 404
