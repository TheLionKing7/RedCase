"""Entitlement gate tests — Feature-Addendum §6 (monetization).

DoD under test (owner 2026-09-17): subscriptions + entitlement_events
tables; require_feature() dependency with 402/403 responses; every gate
decision (ALLOW and DENY) lands in entitlement_events; the gate is wired
into POST /v1/documents/{id}/analyze.

Gate-first contract: require_feature resolves before the route body, so a
DENY surfaces without the document needing to exist — a random document
uuid plus a gated tenant is enough to observe 402/403. The ALLOW case
falls through to the document 404, proving the gate passed.

Seed contract: migration 0004 seeds tenant aetoes as PREMIUM/ACTIVE/
max_seats 10, so the Step A /analyze tests keep working; the DENY cases
provision throwaway tenants inline.
"""

import asyncio
import uuid

import asyncpg
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.test_query_api import make_jwt

JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105 (throwaway test secret)


def _settings(app_db_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=app_db_url,
        supabase_jwt_secret=JWT_SECRET,
    )


async def _provision_tenant(
    app_db_url: str,
    *,
    plan: str = "CORE",
    status: str = "ACTIVE",
    max_seats: int = 0,
    current_seats: int = 0,
) -> str:
    """Create a throwaway tenant with a vault and a subscription row."""
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
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tid
            )
            await conn.execute(
                "INSERT INTO subscriptions (tenant_id, plan, status, max_seats,"
                " current_seats) VALUES ($1, $2, $3, $4, $5)",
                uuid.UUID(tid),
                plan,
                status,
                max_seats,
                current_seats,
            )
    finally:
        await conn.close()
    return tid


async def _gate_events(app_db_url: str, tenant_id: str) -> list[dict]:
    """Read a tenant's entitlement_events (RLS-scoped read)."""
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tenant_id
            )
            rows = await conn.fetch(
                "SELECT feature, decision FROM entitlement_events"
                " WHERE tenant_id = $1 ORDER BY created_at",
                uuid.UUID(tenant_id),
            )
            return [dict(r) for r in rows]
    finally:
        await conn.close()


class TestRequireFeature:
    def test_core_plan_denied_402_with_event(
        self, app_db_url: str
    ) -> None:
        tid = asyncio.run(_provision_tenant(app_db_url))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{uuid.uuid4()}/analyze",
                json={"prompt_pack": "ADVERSAL_BRIEF"},
                headers={"Authorization": f"Bearer {make_jwt(tenant=tid)}"},
            )
        assert resp.status_code == 402
        assert "DENY_PLAN" in resp.json()["detail"]
        events = asyncio.run(_gate_events(app_db_url, tid))
        assert events[-1] == {"feature": "workbench.analyze", "decision": "DENY_PLAN"}

    def test_suspended_tenant_denied_403_with_event(
        self, app_db_url: str
    ) -> None:
        tid = asyncio.run(
            _provision_tenant(app_db_url, plan="PREMIUM", status="SUSPENDED")
        )
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{uuid.uuid4()}/analyze",
                json={"prompt_pack": "ADVERSAL_BRIEF"},
                headers={"Authorization": f"Bearer {make_jwt(tenant=tid)}"},
            )
        assert resp.status_code == 403
        assert "DENY_SUSPENDED" in resp.json()["detail"]
        events = asyncio.run(_gate_events(app_db_url, tid))
        assert events[-1]["decision"] == "DENY_SUSPENDED"

    def test_seat_cap_denied_402_with_event(self, app_db_url: str) -> None:
        tid = asyncio.run(
            _provision_tenant(
                app_db_url, plan="PREMIUM", max_seats=1, current_seats=1
            )
        )
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{uuid.uuid4()}/analyze",
                json={"prompt_pack": "ADVERSAL_BRIEF"},
                headers={"Authorization": f"Bearer {make_jwt(tenant=tid)}"},
            )
        assert resp.status_code == 402
        assert "DENY_SEAT" in resp.json()["detail"]
        events = asyncio.run(_gate_events(app_db_url, tid))
        assert events[-1]["decision"] == "DENY_SEAT"

    def test_premium_active_passes_gate_then_404s_on_unknown_doc(
        self, app_db_url: str
    ) -> None:
        """aetoes (seeded PREMIUM): gate ALLOWs, the route then 404s on the
        random document id — proving the gate passed without running the
        engine. The ALLOW decision must be logged."""
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{uuid.uuid4()}/analyze",
                json={"prompt_pack": "ADVERSAL_BRIEF"},
                headers={
                    "Authorization": f"Bearer {make_jwt(tenant=SEED_TENANT_AETOES)}"
                },
            )
        assert resp.status_code == 404  # gate passed; document unknown
        events = asyncio.run(_gate_events(app_db_url, SEED_TENANT_AETOES))
        allow = [e for e in events if e["decision"] == "ALLOW"]
        assert {"feature": "workbench.analyze", "decision": "ALLOW"} in allow

    def test_gate_event_survives_deny_rollback(
        self, app_db_url: str
    ) -> None:
        """The DENY event must persist even though the denied request's
        transaction rolls back (§6: every gate decision logged)."""
        tid = asyncio.run(_provision_tenant(app_db_url))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/documents/{uuid.uuid4()}/analyze",
                json={"prompt_pack": "ADVERSAL_BRIEF"},
                headers={"Authorization": f"Bearer {make_jwt(tenant=tid)}"},
            )
        assert resp.status_code == 402
        events = asyncio.run(_gate_events(app_db_url, tid))
        assert len(events) == 1  # exactly one event, committed independently
