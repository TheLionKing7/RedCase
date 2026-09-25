"""Public signup + firm invite tests - Part 2 (HANDOFF section 4 growth surface).

DoD under test:
* POST /v1/signup  - an UNAUTHENTICATED, rate-limited write that records a
  PENDING_VERIFICATION firm_signups row keyed by NORMALIZED email (unique index)
  and writes one immutable signup_audit 'apply' row. Without a provider credential
  (dev/CI) it surfaces the raw verify_token for the demo path.
* POST /v1/verify  - activates a PENDING_VERIFICATION application into a provisioned
  tenant + firm vault + CORE subscription (max_seats 3), flips the row ACTIVE,
  clears the token, and writes verify/provision/activate audit rows.
* POST /v1/invites - seat-gated invite: at capacity the invite is DENIED with 402
  upgrade copy and NO seat increment; under capacity the invite succeeds, increments
  current_seats atomically, and maps role -> clearance via app.onboarding (ASSOCIATE
  -> STAFF == the floor, never the ceiling). Only PARTNER/ADMIN may invite (403
  otherwise). Every verdict writes one immutable 'invite' / 'invite_denied'
  signup_audit row.

Email verification uses the httpx provider only when a service role is set; all tests
here run WITHOUT one, so the event loop never touches the network.
"""

import asyncio
import base64
import datetime
import hashlib
import hmac
import json
import time
import uuid
from datetime import UTC

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.onboarding import hash_invite_token, hash_verify_token, new_invite_token, new_verify_token

JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105 (throwaway test secret)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_jwt(
    *,
    sub: str = "partner-1",
    clearance: str = "PARTNER",
    tenant: str = SEED_TENANT_AETOES,
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


def _settings(app_db_url: str) -> Settings:
    """supabase_service_role left unset -> the email provider is skipped (no network)."""
    return Settings(
        _env_file=None,
        database_url=app_db_url,
        supabase_jwt_secret=JWT_SECRET,
    )


async def _seed_subscription(
    app_db_url: str,
    tenant_id: str,
    *,
    plan: str = "CORE",
    status: str = "ACTIVE",
    max_seats: int = 3,
    current_seats: int = 0,
) -> None:
    conn = await asyncpg.connect(app_db_url)
    try:
        # firm_invites FK -> tenants, so the tenant row must exist.
        await conn.execute(
            "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
            uuid.UUID(tenant_id),
            f"Tenant {tenant_id[:8]}",
            f"t-{tenant_id[:8]}",
        )
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            await conn.execute(
                "INSERT INTO subscriptions (tenant_id, plan, status, max_seats,"
                " current_seats) VALUES ($1, $2, $3, $4, $5)"
                " ON CONFLICT (tenant_id) DO NOTHING",
                uuid.UUID(tenant_id),
                plan,
                status,
                max_seats,
                current_seats,
            )
    finally:
        await conn.close()


class TestPublicSignup:
    def test_signup_creates_row_and_returns_demo_token(self, app_db_url: str) -> None:
        email = f"firm-{uuid.uuid4().hex[:8]}@example.com"
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/public/signup",
                json={"email": email, "firm_name": "Test Firm", "jurisdiction": "NG"},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "PENDING_VERIFICATION"
        # Dev/CI fallback surfaces the raw token (no provider credential set).
        assert body["verify_token"]

        async def _check():
            conn = await asyncpg.connect(app_db_url)
            try:
                row = await conn.fetchrow(
                    "SELECT id, status FROM firm_signups WHERE email = $1", email
                )
                audit = await conn.fetchrow(
                    "SELECT step FROM signup_audit WHERE detail = $1",
                    f"signup_id={row['id']}",
                )
            finally:
                await conn.close()
            return row, audit

        row, audit = asyncio.run(_check())
        assert row["status"] == "PENDING_VERIFICATION"
        assert audit["step"] == "apply"

    def test_signup_normalizes_email_and_dedupes(self, app_db_url: str) -> None:
        raw = f"  Case-{uuid.uuid4().hex[:6]}@Example.COM "
        norm = raw.strip().lower()
        with TestClient(create_app(_settings(app_db_url))) as client:
            first = client.post(
                "/v1/public/signup",
                json={"email": raw, "firm_name": "Firm", "jurisdiction": "NG"},
            )
            second = client.post(
                "/v1/public/signup",
                json={"email": norm, "firm_name": "Firm", "jurisdiction": "NG"},
            )
        assert first.status_code == 201
        # Same normalized email -> unique index -> 409 conflict, never a dup row.
        assert second.status_code == 409

    def test_signup_rejects_invalid_email(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/public/signup",
                json={"email": "not-an-email", "firm_name": "Firm"},
            )
        assert resp.status_code == 422

    def test_signup_rate_limited_per_email(self, app_db_url: str) -> None:
        settings = _settings(app_db_url)
        settings.signup_rate_limit_per_email = 1
        email = f"rl-{uuid.uuid4().hex[:8]}@example.com"
        with TestClient(create_app(settings)) as client:
            first = client.post(
                "/v1/public/signup",
                json={"email": email, "firm_name": "Firm"},
            )
            second = client.post(
                "/v1/public/signup",
                json={"email": email, "firm_name": "Firm"},
            )
        assert first.status_code == 201
        assert second.status_code == 429


class TestPublicVerify:
    def test_signup_activation_requires_verified_supabase_session(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            response = client.post(
                "/v1/public/activate",
                json={"email": "owner@example.com", "full_name": "Owner"},
            )
        assert response.status_code == 401

    def test_verify_provisions_tenant_and_activates(self, app_db_url: str) -> None:
        email = f"verify-{uuid.uuid4().hex[:8]}@example.com"
        token = new_verify_token()
        token_hash = hash_verify_token(token)

        # Insert a PENDING_VERIFICATION application directly (equivalent to a prior
        # /signup, but pinning the token so the test owns verification). One
        # asyncio.run per connection lifecycle: asyncpg connections are loop-bound.
        async def _setup() -> uuid.UUID:
            conn = await asyncpg.connect(app_db_url)
            try:
                return await conn.fetchval(
                    "INSERT INTO firm_signups"
                    " (email, firm_name, verify_token_hash, verify_token_expires_at)"
                    " VALUES ($1, $2, $3, now() + interval '1 hour')"
                    " RETURNING id",
                    email,
                    "Verify Firm",
                    token_hash,
                )
            finally:
                await conn.close()

        signup_id = asyncio.run(_setup())

        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/public/verify",
                json={"email": email, "token": token},
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "ACTIVE"
        tenant_id = body["tenant_id"]

        # subscriptions / vaults / signup_audit are RLS-scoped -> set the GUC
        # inside a transaction before reading (fail-closed single-arg form).
        async def _check():
            conn = await asyncpg.connect(app_db_url)
            try:
                async with conn.transaction():
                    await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
                    signup = await conn.fetchrow(
                        "SELECT status, tenant_id, verify_token_hash FROM firm_signups"
                        " WHERE id = $1",
                        signup_id,
                    )
                    sub = await conn.fetchrow(
                        "SELECT plan, max_seats, current_seats, status"
                        " FROM subscriptions WHERE tenant_id = $1",
                        uuid.UUID(tenant_id),
                    )
                    vault = await conn.fetchval(
                        "SELECT count(*) FROM vaults WHERE tenant_id = $1",
                        uuid.UUID(tenant_id),
                    )
                    audit = await conn.fetch(
                        "SELECT step FROM signup_audit WHERE tenant_id = $1 ORDER BY created_at",
                        uuid.UUID(tenant_id),
                    )
            finally:
                await conn.close()
            return signup, sub, vault, audit

        signup, sub, vault, audit = asyncio.run(_check())

        assert signup["status"] == "ACTIVE"
        assert str(signup["tenant_id"]) == tenant_id
        assert signup["verify_token_hash"] is None
        assert sub["plan"] == "CORE"
        assert sub["max_seats"] == 3
        assert sub["current_seats"] == 0
        assert sub["status"] == "ACTIVE"
        assert vault == 1
        steps = [r["step"] for r in audit]
        assert "verify" in steps and "provision" in steps and "activate" in steps

    def test_verify_rejects_bad_token(self, app_db_url: str) -> None:
        email = f"bad-{uuid.uuid4().hex[:8]}@example.com"
        token = new_verify_token()

        async def _setup() -> None:
            conn = await asyncpg.connect(app_db_url)
            try:
                await conn.execute(
                    "INSERT INTO firm_signups"
                    " (email, firm_name, verify_token_hash, verify_token_expires_at)"
                    " VALUES ($1, $2, $3, now() + interval '1 hour')",
                    email,
                    "Bad Firm",
                    hash_verify_token(token),
                )
            finally:
                await conn.close()

        asyncio.run(_setup())

        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/public/verify",
                json={"email": email, "token": "wrong-token"},
            )
        assert resp.status_code == 400

    def test_verify_rejects_expired_token(self, app_db_url: str) -> None:
        email = f"exp-{uuid.uuid4().hex[:8]}@example.com"
        token = new_verify_token()

        async def _setup() -> None:
            conn = await asyncpg.connect(app_db_url)
            try:
                await conn.execute(
                    "INSERT INTO firm_signups"
                    " (email, firm_name, verify_token_hash, verify_token_expires_at)"
                    " VALUES ($1, $2, $3, $4)",
                    email,
                    "Exp Firm",
                    hash_verify_token(token),
                    datetime.datetime.now(UTC) - datetime.timedelta(hours=1),
                )
            finally:
                await conn.close()

        asyncio.run(_setup())

        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/public/verify",
                json={"email": email, "token": token},
            )
        assert resp.status_code == 400


class TestInvites:
    def test_invite_succeeds_and_increments_seat(self, app_db_url: str) -> None:
        tid = str(uuid.uuid4())
        # Throwaway tenant with a 3-seat CORE subscription.
        asyncio.run(_seed_subscription(app_db_url, tid, max_seats=3, current_seats=0))
        email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/invites",
                json={"email": email, "role": "ASSOCIATE"},
                headers={"Authorization": f"Bearer {make_jwt(tenant=tid)}"},
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "PENDING"
        # ASSOCIATE -> STAFF: floor, never the ceiling (RLS ladder lynchpin).
        assert body["clearance"] == "STAFF"

        async def _check():
            conn = await asyncpg.connect(app_db_url)
            try:
                async with conn.transaction():
                    await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tid)
                    sub = await conn.fetchrow(
                        "SELECT max_seats, current_seats FROM subscriptions WHERE tenant_id = $1",
                        uuid.UUID(tid),
                    )
                    audit = await conn.fetchrow(
                        "SELECT step FROM signup_audit WHERE tenant_id = $1 AND step = 'invite'",
                        uuid.UUID(tid),
                    )
            finally:
                await conn.close()
            return sub, audit

        sub, audit = asyncio.run(_check())
        assert sub["current_seats"] == 1
        assert sub["max_seats"] == 3
        assert audit is not None

    def test_invite_denied_at_capacity_without_seat_increment(self, app_db_url: str) -> None:
        tid = str(uuid.uuid4())
        asyncio.run(_seed_subscription(app_db_url, tid, max_seats=1, current_seats=1))
        email = f"over-{uuid.uuid4().hex[:8]}@example.com"
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/invites",
                json={"email": email, "role": "SENIOR"},
                headers={"Authorization": f"Bearer {make_jwt(tenant=tid)}"},
            )
        assert resp.status_code == 402
        assert "DENY_SEAT" in resp.json()["detail"]

        async def _check():
            conn = await asyncpg.connect(app_db_url)
            try:
                async with conn.transaction():
                    await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tid)
                    sub = await conn.fetchrow(
                        "SELECT current_seats FROM subscriptions WHERE tenant_id = $1",
                        uuid.UUID(tid),
                    )
                    denied = await conn.fetchrow(
                        "SELECT step FROM signup_audit WHERE tenant_id = $1"
                        " AND step = 'invite_denied'",
                        uuid.UUID(tid),
                    )
            finally:
                await conn.close()
            return sub, denied

        sub, denied = asyncio.run(_check())
        # No increment on a DENY.
        assert sub["current_seats"] == 1
        assert denied is not None

    def test_invite_forbidden_for_non_partner(self, app_db_url: str) -> None:
        tid = str(uuid.uuid4())
        asyncio.run(_seed_subscription(app_db_url, tid, max_seats=3, current_seats=0))
        email = f"staff-{uuid.uuid4().hex[:8]}@example.com"
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/invites",
                json={"email": email, "role": "STAFF"},
                headers={"Authorization": f"Bearer {make_jwt(tenant=tid, clearance='STAFF')}"},
            )
        assert resp.status_code == 403

    def test_invite_maps_partner_role_to_partner_clearance(self, app_db_url: str) -> None:
        tid = str(uuid.uuid4())
        asyncio.run(_seed_subscription(app_db_url, tid, max_seats=3, current_seats=0))
        email = f"newpartner-{uuid.uuid4().hex[:8]}@example.com"
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/invites",
                json={"email": email, "role": "PARTNER"},
                headers={"Authorization": f"Bearer {make_jwt(tenant=tid)}"},
            )
        assert resp.status_code == 201
        assert resp.json()["clearance"] == "PARTNER"

    def test_invite_rejects_unknown_role(self, app_db_url: str) -> None:
        tid = str(uuid.uuid4())
        asyncio.run(_seed_subscription(app_db_url, tid, max_seats=3, current_seats=0))
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/invites",
                json={"email": "x@example.com", "role": "PARALEGAL"},
                headers={"Authorization": f"Bearer {make_jwt(tenant=tid)}"},
            )
        assert resp.status_code == 422

    def test_accept_rejects_unknown_token(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/invites/accept",
                json={"token": "no-such-token-123", "password": "superSecret9"},
            )
        assert resp.status_code == 400


async def _seed_invite(
    app_db_url: str,
    tenant_id: str,
    email: str,
    *,
    role: str = "ASSOCIATE",
    clearance: str = "STAFF",
    expires_in_s: int = 3600,
) -> str:
    """Insert a PENDING firm_invites row (RLS-scoped) and return the RAW token."""
    token = new_invite_token()
    token_hash = hash_invite_token(token)
    expires = datetime.datetime.now(UTC) + datetime.timedelta(seconds=expires_in_s)
    conn = await asyncpg.connect(app_db_url)
    try:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant_id)
            await conn.execute(
                "INSERT INTO firm_invites"
                " (tenant_id, invited_email, role, clearance, invited_by,"
                "  invite_token_hash, invite_token_expires_at)"
                " VALUES ($1, $2, $3, $4, 'partner-1', $5, $6)",
                uuid.UUID(tenant_id),
                email,
                role,
                clearance,
                token_hash,
                expires,
            )
    finally:
        await conn.close()
    return token


class TestInviteAccept:
    """POST /v1/invites/accept - Slice 1 backend close."""

    def test_accept_creates_user_with_invite_clearance_and_is_single_use(
        self, app_db_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        tid = str(uuid.uuid4())
        asyncio.run(_seed_subscription(app_db_url, tid, max_seats=3, current_seats=1))
        email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
        token = asyncio.run(
            _seed_invite(app_db_url, tid, email, role="ASSOCIATE", clearance="STAFF")
        )
        captured: dict = {}

        async def fake_create(settings, email, password, name, tenant_id, clearance):
            captured["email"] = email
            captured["password"] = password
            captured["clearance"] = clearance
            captured["tenant"] = tenant_id
            return "user-created-123"

        monkeypatch.setattr("app.routers.invites._create_supabase_user", fake_create)
        app = create_app(_settings(app_db_url))
        with TestClient(app) as client:
            resp = client.post(
                "/v1/invites/accept",
                json={"token": token, "password": "superSecret9"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ACCEPTED"
        assert body["tenant_id"] == tid
        assert body["clearance"] == "STAFF"
        assert captured["clearance"] == "STAFF"
        assert captured["email"] == email

        async def _check() -> None:
            conn = await asyncpg.connect(app_db_url)
            try:
                async with conn.transaction():
                    await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tid)
                    row = await conn.fetchrow(
                        "SELECT status, accepted_user_ref FROM firm_invites"
                        " WHERE invited_email = $1 AND tenant_id = $2::uuid",
                        email,
                        uuid.UUID(tid),
                    )
                    audit = await conn.fetchrow(
                        "SELECT step FROM signup_audit WHERE step = 'invite_accepted'",
                    )
            finally:
                await conn.close()
            assert row is not None
            assert row["status"] == "ACCEPTED"
            assert row["accepted_user_ref"] == "user-created-123"
            assert audit is not None

        asyncio.run(_check())

        with TestClient(app) as client:
            resp2 = client.post(
                "/v1/invites/accept",
                json={"token": token, "password": "superSecret9"},
            )
        assert resp2.status_code == 400

    def test_accept_rejects_expired_token(self, app_db_url: str) -> None:
        tid = str(uuid.uuid4())
        asyncio.run(_seed_subscription(app_db_url, tid, max_seats=3, current_seats=1))
        token = asyncio.run(
            _seed_invite(app_db_url, tid, "expired@example.com", expires_in_s=-60)
        )
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/invites/accept",
                json={"token": token, "password": "superSecret9"},
            )
        assert resp.status_code == 400

    def test_accept_ignores_client_clearance_injection(
        self, app_db_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A forged clearance in the body must be ignored - the grant comes from the invite."""
        tid = str(uuid.uuid4())
        asyncio.run(_seed_subscription(app_db_url, tid, max_seats=3, current_seats=1))
        email = f"inject-{uuid.uuid4().hex[:8]}@example.com"
        token = asyncio.run(
            _seed_invite(app_db_url, tid, email, role="STAFF", clearance="STAFF")
        )
        captured: dict = {}

        async def fake_create(settings, email, password, name, tenant_id, clearance):
            captured["clearance"] = clearance
            return None

        monkeypatch.setattr("app.routers.invites._create_supabase_user", fake_create)
        with TestClient(create_app(_settings(app_db_url))) as client:
            resp = client.post(
                "/v1/invites/accept",
                json={
                    "token": token,
                    "password": "superSecret9",
                    "clearance": "PARTNER",
                },
            )
        assert resp.status_code == 200
        assert captured["clearance"] == "STAFF"
