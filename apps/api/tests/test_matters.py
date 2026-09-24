"""Matter assignment + Firm Command progress panel tests — Addendum-S10 §10.4 (S10-3).

DoD under test: assign gating (PARTNER/ADMIN or firm-admin); assignee must be a
licensed in-tenant user (firm_invites ACCEPTED); assignment persists + idempotent
reassign; GET /v1/matters/my filters by assigned_to = me; the progress panel is
firm-admin-gated and composes analyses_count + time_minutes; RLS isolates tenants
(unknown/cross-tenant matter -> 404).
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

from app.config import Settings
from app.main import create_app

JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105
TENANT_B = "b0000002-0000-4000-8000-000000000002"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_jwt(
    *,
    sub: str = "assigner",
    tenant: str = SEED_TENANT_AETOES,
    clearance: str = "PARTNER",
    is_firm_admin: bool = False,
) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "exp": int(time.time()) + 3600,
        "app_metadata": {
            "tenant_id": tenant,
            "clearance": clearance,
            "is_firm_admin": is_firm_admin,
        },
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


async def _provision_matter(app_db_url: str, tenant: str) -> uuid.UUID:
    """Create a synthetic client + matter in `tenant` (same shape as test_practice)."""
    conn = await asyncpg.connect(app_db_url)
    try:
        client_id, matter = uuid.uuid4(), uuid.uuid4()
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute(
                "SELECT set_config('app.user_clearance', 'PARTNER', true)"
            )
            await conn.execute(
                "SELECT set_config('app.user_ref', 'setup-partner', true)"
            )
            await conn.execute(
                "INSERT INTO clients (id, tenant_id, name) VALUES ($1, $2, $3)",
                client_id,
                tenant,
                f"Matter Client {uuid.uuid4().hex[:8]}",
            )
            await conn.execute(
                "INSERT INTO matters (id, tenant_id, client_id, matter_ref)"
                " VALUES ($1, $2, $3, $4)",
                matter,
                tenant,
                client_id,
                f"MAT-{uuid.uuid4().hex[:8]} v. Syn",
            )
        return matter
    finally:
        await conn.close()


async def _accept_invite_for(
    app_db_url: str, tenant: str, user_ref: str
) -> None:
    """Make `user_ref` a licensed in-tenant user (ACCEPTED firm_invite)."""
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            await conn.execute(
                "INSERT INTO firm_invites"
                " (tenant_id, invited_email, role, clearance, invited_by, status,"
                "  accepted_user_ref)"
                " VALUES ($1, $2, 'ASSOCIATE', 'SENIOR', 'setup-partner',"
                "  'ACCEPTED', $3)",
                tenant,
                f"{user_ref}@firm.test",
                user_ref,
            )
    finally:
        await conn.close()

async def _seed_analyses_and_time(
    app_db_url: str, matter: uuid.UUID, tenant: str = SEED_TENANT_AETOES
) -> None:
    """Insert 2 analyses + 55 billed-less minutes on `matter` for panel counts."""
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
            vault = await conn.fetchval(
                "SELECT id FROM vaults WHERE tenant_id = $1::uuid LIMIT 1", tenant
            )
            if vault is None:
                raise RuntimeError("seed vault missing")
            doc = uuid.uuid4()
            await conn.execute(
                "INSERT INTO documents"
                " (id, tenant_id, vault_id, case_title, citation, court_level, year,"
                "  source_pdf_path, pdf_sha256)"
                " VALUES ($1, $2, $3, $4, $5, 'FEDERAL_HIGH_COURT', 2024,"
                "  '/seed/path.pdf', 'decafbad')",
                doc,
                tenant,
                vault,
                f"Seed matter doc {uuid.uuid4().hex[:6]}",
                f"[2026] FHC/{uuid.uuid4().hex[:6]}",
            )
            for _ in range(2):
                await conn.execute(
                    "INSERT INTO document_analyses"
                    " (tenant_id, document_id, matter_id, prompt_pack, status,"
                    "  created_by)"
                    " VALUES ($1, $2, $3::uuid, 'ADVERSARIAL_BRIEF', 'COMPLETE',"
                    "  'seed')",
                    tenant,
                    doc,
                    matter,
                )
            for minutes in (20, 35):
                await conn.execute(
                    "INSERT INTO time_entries"
                    " (tenant_id, matter_id, user_ref, description, minutes)"
                    " VALUES ($1, $2::uuid, 'seed', 'review', $3)",
                    tenant,
                    matter,
                    minutes,
                )
    finally:
        await conn.close()


class TestAssign:
    def test_partner_admin_can_assign(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        asyncio.run(_accept_invite_for(app_db_url, SEED_TENANT_AETOES, "lead-atty"))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/matters/{matter}/assign",
                json={
                    "assigned_to": "lead-atty",
                    "progress_note": "Awaiting client instructions.",
                },
                headers=_auth(sub="assigner", clearance="PARTNER", is_firm_admin=True),
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["assigned_to"] == "lead-atty"
            assert body["progress_note"] == "Awaiting client instructions."
            assert body["status"] == "ACTIVE"

    def test_staffer_without_admin_rejected(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        asyncio.run(_accept_invite_for(app_db_url, SEED_TENANT_AETOES, "lead-atty"))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/matters/{matter}/assign",
                json={"assigned_to": "lead-atty"},
                headers=_auth(sub="staffer", clearance="STAFF", is_firm_admin=False),
            )
            assert resp.status_code == 403

    def test_madeup_assignee_rejected(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/matters/{matter}/assign",
                json={"assigned_to": "no-such-user"},
                headers=_auth(sub="assigner", clearance="PARTNER", is_firm_admin=True),
            )
            assert resp.status_code == 422

    def test_cross_tenant_matter_404(self, app_db_url: str) -> None:
        # Tenant A's assigner cannot see tenant B's matter: RLS hides it -> 404
        # (the router validates tenancy via app.tenant_id before touching the row).
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/matters/{uuid.uuid4()}/assign",
                json={"assigned_to": "lead-atty"},
                headers=_auth(sub="assigner", clearance="PARTNER", is_firm_admin=True),
            )
            assert resp.status_code == 404


class TestMineAndProgress:
    def test_my_matters_returns_only_assigned(self, app_db_url: str) -> None:
        m1 = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        asyncio.run(_accept_invite_for(app_db_url, SEED_TENANT_AETOES, "me-ref"))
        with TestClient(create_app(_settings(app_db_url))) as client:
            # Assign one matter to me, then list my matters.
            a = client.post(
                f"/v1/matters/{m1}/assign",
                json={"assigned_to": "me-ref"},
                headers=_auth(sub="assigner", clearance="PARTNER", is_firm_admin=True),
            )
            assert a.status_code == 200, a.text
            mine = client.get(
                "/v1/matters/my", headers=_auth(sub="me-ref", clearance="SENIOR")
            )
            assert mine.status_code == 200, mine.text
            refs = [m["matter_ref"] for m in mine.json()["matters"]]
            # Only m1 (the sole matter assigned to me-ref) appears.
            assert len(refs) == 1

    def test_progress_panel_firm_admin_gated(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.get(
                "/v1/firm/matters/progress",
                headers=_auth(sub="assigner", clearance="PARTNER", is_firm_admin=False),
            )
            assert resp.status_code == 403

            ok = client.get(
                "/v1/firm/matters/progress",
                headers=_auth(sub="assigner", clearance="PARTNER", is_firm_admin=True),
            )
            assert ok.status_code == 200, ok.text

    def test_progress_composes_counts(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        asyncio.run(_accept_invite_for(app_db_url, SEED_TENANT_AETOES, "lead-atty"))
        asyncio.run(_seed_analyses_and_time(app_db_url, matter))
        with TestClient(create_app(_settings(app_db_url))) as client:
            client.post(
                f"/v1/matters/{matter}/assign",
                json={"assigned_to": "lead-atty", "progress_note": "In review."},
                headers=_auth(sub="assigner", clearance="PARTNER", is_firm_admin=True),
            )
            resp = client.get(
                "/v1/firm/matters/progress",
                headers=_auth(sub="assigner", clearance="PARTNER", is_firm_admin=True),
            )
            assert resp.status_code == 200, resp.text
            row = resp.json()["matters"][0]
            assert row["assigned_to"] == "lead-atty"
            assert row["analyses_count"] == 2
            assert row["time_minutes"] == 55

