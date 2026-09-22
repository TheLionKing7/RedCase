"""Firm Command — firm-admin capability (Addendum §8.5, audit H3).

Admin capability is an ORTHOGONAL dimension to clearance: the ``is_firm_admin``
flag arrives on the JWT ``app_metadata`` claim (fail-closed false in deps.py). All
Firm Command endpoints are gated by ``require_firm_admin``:

  * A caller WITHOUT the flag — ANY clearance, including a PARTNER — gets 403 on
    every admin surface (never UI hiding; server-side enforcement).
  * A caller WITH the flag gets the seats / invites / transparency / ledger /
    settings surfaces.
  * Admin grant/revoke (POST /admin/grants) works only for admins and lands an
    immutable row on the append-only ``firm_admins`` ledger — and, per the
    append-only grant in conftest, that row can never be updated or deleted by the
    app role.

Seed contract: migration 0020 seeds a GRANTED row for the managing partner of tenant
zero (``mp-aetoes``), which appears in the ledger/transparency feeds.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

JWT_SECRET = "test-secret"  # noqa: S105 (throwaway test-only shared secret)

ADMIN_REF = "mp-aetoes"  # migration 0020 seed: managing partner of tenant zero
STAFF_REF = "staff-user"
PARTNER_REF = "partner-user"


def make_jwt(
    *,
    sub: str = STAFF_REF,
    tenant: str = SEED_TENANT_AETOES,
    clearance: str = "STAFF",
    is_firm_admin: bool = False,
) -> str:
    """HS256 JWT matching app.deps.verify_supabase_jwt's claim contract."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "exp": time.time() + 3600,
        "app_metadata": {
            "tenant_id": tenant,
            "clearance": clearance,
            "is_firm_admin": is_firm_admin,
        },
    }

    def b64(d: dict) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
        )

    signing = f"{b64(header)}.{b64(payload)}"
    sig = base64.urlsafe_b64encode(
        hmac.new(JWT_SECRET.encode(), signing.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{signing}.{sig}"


def _settings(app_db_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=app_db_url,
        supabase_jwt_secret=JWT_SECRET,
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_firm_admin_gate_rejects_non_admin(app_db_url: str) -> None:
    """§8.5: a non-admin (ANY clearance incl. PARTNER) gets 403 on every surface."""
    with TestClient(create_app(_settings(app_db_url))) as client:
        token_staff = make_jwt(sub=STAFF_REF, clearance="STAFF", is_firm_admin=False)
        token_partner = make_jwt(sub=PARTNER_REF, clearance="PARTNER", is_firm_admin=False)

        for token in (token_staff, token_partner):
            for path in (
                "/v1/firm/admin/overview",
                "/v1/firm/admin/invites",
                "/v1/firm/admin/transparency",
                "/v1/firm/admin/admins",
                "/v1/firm/admin/settings",
            ):
                resp = client.get(path, headers=_headers(token))
                assert resp.status_code == 403, f"{path} → {resp.status_code}"

            # Grant/revoke is an admin act too.
            resp = client.post(
                "/v1/firm/admin/grants",
                headers=_headers(token),
                json={"user_ref": STAFF_REF, "action": "GRANTED"},
            )
            assert resp.status_code == 403


def test_firm_admin_overview_and_settings(app_db_url: str) -> None:
    """An admin can read seats and firm settings."""
    with TestClient(create_app(_settings(app_db_url))) as client:
        token = make_jwt(sub=ADMIN_REF, is_firm_admin=True)

        resp = client.get("/v1/firm/admin/overview", headers=_headers(token))
        assert resp.status_code == 200
        seats = resp.json()["seats"]
        # Seed: tenant zero is PREMIUM / ACTIVE / max 10 (migration 0004).
        assert seats["plan"] == "PREMIUM"
        assert seats["status"] == "ACTIVE"
        assert seats["max_seats"] == 10

        resp = client.get("/v1/firm/admin/settings", headers=_headers(token))
        assert resp.status_code == 200
        assert resp.json()["firm"]["slug"] == "aetoes"


def test_firm_admin_ledger_has_seeded_default(app_db_url: str) -> None:
    """Migration 0020 seeded the managing partner as default admin (GRANTED)."""
    with TestClient(create_app(_settings(app_db_url))) as client:
        token = make_jwt(sub=ADMIN_REF, is_firm_admin=True)

        resp = client.get("/v1/firm/admin/admins", headers=_headers(token))
        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert any(
            e["user_ref"] == ADMIN_REF and e["action"] == "GRANTED" for e in entries
        )


def test_admin_grant_is_append_only(app_db_url: str) -> None:
    """POST /admin/grants records a row AND the app role cannot update/delete it."""
    with TestClient(create_app(_settings(app_db_url))) as client:
        token = make_jwt(sub=ADMIN_REF, is_firm_admin=True)

        resp = client.post(
            "/v1/firm/admin/grants",
            headers=_headers(token),
            json={"user_ref": "new-admin", "action": "GRANTED"},
        )
        assert resp.status_code == 201
        event_id = resp.json()["id"]
        uuid.UUID(event_id)
        assert resp.json()["action"] == "GRANTED"
        assert resp.json()["granted_by"] == ADMIN_REF

        # The app role cannot mutate the ledger (append-only DB grant).
        async def _try_mutate() -> None:
            conn = await asyncpg.connect(app_db_url)
            try:
                await conn.execute(
                    "UPDATE firm_admins SET action = 'REVOKED' WHERE id = $1::uuid",
                    uuid.UUID(event_id),
                )
            finally:
                await conn.close()

        with pytest.raises(asyncpg.PostgresError):
            asyncio.run(_try_mutate())


def test_admin_transparency_is_zdr_clean(app_db_url: str) -> None:
    """Transparency feed exposes metadata only — never answer text/bodies."""
    with TestClient(create_app(_settings(app_db_url))) as client:
        token = make_jwt(sub=ADMIN_REF, is_firm_admin=True)

        resp = client.get("/v1/firm/admin/transparency", headers=_headers(token))
        assert resp.status_code == 200
        body = resp.json()
        for item in body["query"]:
            assert "answer_text" not in item
            assert "citations" not in item
        assert any(
            e["user_ref"] == ADMIN_REF and e["action"] == "GRANTED"
            for e in body["admins"]
        )


