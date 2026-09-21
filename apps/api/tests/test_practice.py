"""Practice operations tests — Addendum §9.1, task 3.9 sub-task 1 (time capture).

DoD under test: time_entries schema (tenant RLS, matter FK, idempotency);
matter-scoped POST /v1/matters/{id}/time records minutes with entitlement
gating (ops.time, CORE); the `/time` slash command in a matter channel records
a time entry + reflects a channel message; idempotency collapses retries; RLS
isolates tenants (a second tenant reads zero rows at SQL level).

Test helper: each matter is created under a synthetic client in the seeded aetoes
tenant (same setup as test_vault_a_ingest).
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


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_jwt(*, sub: str = "time-user", tenant: str = SEED_TENANT_AETOES) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "exp": int(time.time()) + 3600,
        "app_metadata": {"tenant_id": tenant, "clearance": "STAFF"},
    }
    seg = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    sig = hmac.new(JWT_SECRET.encode(), seg.encode(), hashlib.sha256).digest()
    return f"{seg}.{_b64url(sig)}"


def _auth(*, sub: str = "time-user", tenant: str = SEED_TENANT_AETOES) -> dict:
    return {"Authorization": f"Bearer {make_jwt(sub=sub, tenant=tenant)}"}


def _settings(app_db_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=app_db_url,
        supabase_jwt_secret=JWT_SECRET,
    )


async def _provision_matter(app_db_url: str, tenant: str) -> uuid.UUID:
    conn = await asyncpg.connect(app_db_url)
    try:
        client_id, matter = uuid.uuid4(), uuid.uuid4()
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tenant
            )
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
                f"Practice Client {uuid.uuid4().hex[:8]}",
            )
            await conn.execute(
                "INSERT INTO matters (id, tenant_id, client_id, matter_ref)"
                " VALUES ($1, $2, $3, $4)",
                matter,
                tenant,
                client_id,
                f"PRAC-{uuid.uuid4().hex[:8]} v. Syn",
            )
        return matter
    finally:
        await conn.close()


async def _provision_matter_channel(
    app_db_url: str, tenant: str, matter: uuid.UUID
) -> uuid.UUID:
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tenant
            )
            channel_id = await conn.fetchval(
                "SELECT provision_matter_channel($1, $2, 'Claimant', 'Defendant')",
                uuid.UUID(tenant),
                matter,
            )
            # The `/time` caller must be a participant of the MATTER channel, or
            # can_read_channel() denies /time and the reflection (participant_send).
            await conn.execute(
                "INSERT INTO channel_participants"
                " (tenant_id, channel_id, participant_ref, participant_kind)"
                " VALUES ($1, $2, 'time-user', 'USER')"
                " ON CONFLICT (channel_id, participant_ref) DO NOTHING",
                uuid.UUID(tenant),
                channel_id,
            )
            return channel_id
    finally:
        await conn.close()


async def _count_entries_for_tenant(
    app_db_url: str, tenant: str, matter: uuid.UUID
) -> int:
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tenant
            )
            return await conn.fetchval(
                "SELECT COUNT(*) FROM time_entries WHERE matter_id = $1::uuid", matter
            )
    finally:
        await conn.close()

class TestPostTime:
    def test_records_minutes_and_total(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/matters/{matter}/time",
                json={"description": "reviewed affidavit", "minutes": 30},
                headers=_auth(),
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["minutes"] == 30
            assert body["total_minutes"] == 30
            assert body["description"] == "reviewed affidavit"

            second = client.post(
                f"/v1/matters/{matter}/time",
                json={"description": "drafted reply", "minutes": 45},
                headers=_auth(),
            )
            assert second.status_code == 201
            assert second.json()["total_minutes"] == 75

    def test_zero_minutes_rejected(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/matters/{matter}/time",
                json={"description": "bad", "minutes": 0},
                headers=_auth(),
            )
            assert resp.status_code == 422

    def test_foreign_matter_not_found(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/matters/{uuid.uuid4()}/time",
                json={"description": "x", "minutes": 10},
                headers=_auth(),
            )
            assert resp.status_code == 404


class TestIdempotency:
    def test_duplicate_key_collapses_to_one_entry(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        key = f"k-{uuid.uuid4().hex}"
        with TestClient(create_app(_settings(app_db_url))) as client:
            first = client.post(
                f"/v1/matters/{matter}/time",
                json={"description": "x", "minutes": 20, "idempotency_key": key},
                headers=_auth(),
            )
            second = client.post(
                f"/v1/matters/{matter}/time",
                json={"description": "x", "minutes": 20, "idempotency_key": key},
                headers=_auth(),
            )
        assert first.status_code == 201 and second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        n = asyncio.run(
            _count_entries_for_tenant(app_db_url, SEED_TENANT_AETOES, matter)
        )
        assert n == 1

    def test_distinct_keys_are_two_entries(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            a = client.post(
                f"/v1/matters/{matter}/time",
                json={
                    "description": "a",
                    "minutes": 10,
                    "idempotency_key": f"a-{uuid.uuid4().hex}",
                },
                headers=_auth(),
            )
            b = client.post(
                f"/v1/matters/{matter}/time",
                json={
                    "description": "b",
                    "minutes": 15,
                    "idempotency_key": f"b-{uuid.uuid4().hex}",
                },
                headers=_auth(),
            )
        assert a.json()["id"] != b.json()["id"]


class TestTimeIsolation:
    async def _provision_tenant_b(self, app_db_url: str) -> str:
        # A second tenant must exist (matters.tenant_id REFERENCES tenants(id)).
        tenant_b = str(uuid.uuid4())
        conn = await asyncpg.connect(app_db_url)
        try:
            await conn.execute(
                "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
                uuid.UUID(tenant_b),
                f"Tenant {tenant_b[:8]}",
                f"t-{tenant_b[:8]}",
            )
        finally:
            await conn.close()
        return tenant_b

    def test_other_tenant_reads_zero_rows(self, app_db_url: str) -> None:
        tenant_b = asyncio.run(self._provision_tenant_b(app_db_url))

        # Tenant B records its own matter + time so the row exists for it.
        matter_b = asyncio.run(_provision_matter(app_db_url, tenant_b))
        with TestClient(create_app(_settings(app_db_url))) as client:
            assert (
                client.post(
                    f"/v1/matters/{matter_b}/time",
                    json={"description": "b", "minutes": 15},
                    headers=_auth(tenant=tenant_b),
                ).status_code
                == 201
            )

        # A different matter owned by the seed tenant with time on it.
        matter_a = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            client.post(
                f"/v1/matters/{matter_a}/time",
                json={"description": "a", "minutes": 30},
                headers=_auth(),
            )

        # Tenant B reads ZERO rows of tenant A's matter at SQL level (RLS).
        assert (
            asyncio.run(
                _count_entries_for_tenant(app_db_url, tenant_b, matter_a)
            )
            == 0
        )
        # And tenant B still sees its own entries.
        assert (
            asyncio.run(
                _count_entries_for_tenant(app_db_url, tenant_b, matter_b)
            )
            == 1
        )


class TestChannelTimeCommand:
    def test_time_command_in_matter_channel(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        channel_id = asyncio.run(
            _provision_matter_channel(app_db_url, SEED_TENANT_AETOES, matter)
        )
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                f"/v1/channels/{channel_id}/messages",
                json={
                    "body": "/time 30 reviewed affidavit",
                    "idempotency_key": f"c-{uuid.uuid4().hex}",
                },
                headers=_auth(),
            )
            assert resp.status_code == 201
            listed = client.get(f"/v1/matters/{matter}/time", headers=_auth())
            assert listed.status_code == 200
            assert listed.json()["total_minutes"] == 30

