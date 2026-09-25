"""Firm KYC — Addendum S10.2 (S10-1).

The KYC step of the onboarding wizard. Firm-admin-only (the orthogonal
``is_firm_admin`` capability, Addendum 8.5 — never derived from clearance). KYC
documents are PARTNER_RESTRICTED-class content: this surface stores only storage
PATHS (never document bytes), and verification_status starts PENDING with no client path
to VERIFIED/REJECTED (a manual ops step for tenant zero).

  * A non-admin (ANY clearance, including PARTNER) gets 403 on GET and POST.
  * An admin can submit a KYC packet (rc + ID document paths) and read it back.
  * Submitting without both documents is rejected (422).
  * RLS tenant-scoping: an admin of a DIFFERENT tenant cannot see/claim the row.

ZDR: firm_kyc carries paths + status, never document content.
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
from app.routers.firm_storage import MAX_UPLOAD_BYTES, _sniff_content_type

JWT_SECRET = "test-secret"  # noqa: S105 (throwaway test-only shared secret)

ADMIN_REF = "mp-aetoes"  # migration 0020 seed: managing partner of tenant zero
STAFF_REF = "staff-user"
PARTNER_REF = "partner-user"
OTHER_TENANT = "b0000000-0000-4000-8000-000000000002"


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


_admin = make_jwt(sub=ADMIN_REF, is_firm_admin=True)
_partner_no_admin = make_jwt(sub=PARTNER_REF, clearance="PARTNER", is_firm_admin=False)
_staff = make_jwt(sub=STAFF_REF, clearance="STAFF", is_firm_admin=False)


def test_upload_signature_sniffer_accepts_only_expected_file_headers() -> None:
    assert _sniff_content_type(b"%PDF-1.7\nbody") == "application/pdf"
    assert _sniff_content_type(b"\xff\xd8\xff\xe0image") == "image/jpeg"
    assert _sniff_content_type(b"\x89PNG\r\n\x1a\nimage") == "image/png"
    assert _sniff_content_type(b"not a pdf") is None


def test_upload_size_limit_is_ten_megabytes() -> None:
    assert MAX_UPLOAD_BYTES == 10 * 1024 * 1024


def test_upload_rejects_extension_spoofed_content(app_db_url: str) -> None:
    with TestClient(create_app(_settings(app_db_url))) as client:
        response = client.post(
            "/v1/firm/assets/rc-document",
            headers={**_headers(_admin), "Content-Type": "application/pdf"},
            content=b"<html>not a PDF</html>",
        )
        assert response.status_code == 415


def test_upload_rejects_payload_over_cap(app_db_url: str) -> None:
    with TestClient(create_app(_settings(app_db_url))) as client:
        response = client.post(
            "/v1/firm/assets/personal-id",
            headers={**_headers(_admin), "Content-Type": "application/pdf"},
            content=b"%PDF-1.7\n" + (b"x" * MAX_UPLOAD_BYTES),
        )
        assert response.status_code == 413


def test_asset_upload_requires_firm_admin(app_db_url: str) -> None:
    with TestClient(create_app(_settings(app_db_url))) as client:
        for token in (_staff, _partner_no_admin):
            response = client.post(
                "/v1/firm/assets/rc-document",
                headers={**_headers(token), "Content-Type": "application/pdf"},
                content=b"%PDF-1.7\nprivate bytes",
            )
            assert response.status_code == 403


def test_kyc_rejects_non_admin(app_db_url: str) -> None:
    """§8.5: a non-admin (STAFF or even a PARTNER w/o the flag) gets 403."""
    with TestClient(create_app(_settings(app_db_url))) as client:
        payload = {
            "rc_path": "kyc/aetoes/rc.pdf",
            "id_document_path": "kyc/aetoes/id.pdf",
        }
        for token in (_staff, _partner_no_admin):
            assert (
                client.get("/v1/firm/kyc", headers=_headers(token)).status_code == 403
            )
            assert (
                client.post(
                    "/v1/firm/kyc", headers=_headers(token), json=payload
                ).status_code
                == 403
            )


def test_kyc_submit_requires_both_documents(app_db_url: str) -> None:
    """A KYC packet needs both the firm RC and the administrator ID document."""
    with TestClient(create_app(_settings(app_db_url))) as client:
        resp = client.post(
            "/v1/firm/kyc",
            headers=_headers(_admin),
            json={"rc_path": "kyc/aetoes/rc.pdf"},
        )
        assert resp.status_code == 422


def test_kyc_submit_and_read_back(app_db_url: str) -> None:
    """An admin submits a KYC packet and reads it back PENDING."""
    with TestClient(create_app(_settings(app_db_url))) as client:
        payload = {
            "firm_website": "https://aetoes.example",
            "rc_path": "kyc/aetoes/rc.pdf",
            "id_document_path": "kyc/aetoes/admin-id.pdf",
            "id_document_type": "passport",
        }
        resp = client.post("/v1/firm/kyc", headers=_headers(_admin), json=payload)
        assert resp.status_code == 200
        assert resp.json()["kyc"]["verification_status"] == "PENDING"

        resp = client.get("/v1/firm/kyc", headers=_headers(_admin))
        assert resp.status_code == 200
        kyc = resp.json()["kyc"]
        assert kyc["rc_path"] == "kyc/aetoes/rc.pdf"
        assert kyc["id_document_path"] == "kyc/aetoes/admin-id.pdf"
        assert kyc["id_document_type"] == "passport"
        assert kyc["verification_status"] == "PENDING"
        assert kyc["reviewed_by"] is None


def test_kyc_is_tenant_scoped(app_db_url: str) -> None:
    """RLS: an admin of another tenant cannot read this firm's KYC row."""
    other_admin = make_jwt(sub="admin-b", tenant=OTHER_TENANT, is_firm_admin=True)

    with TestClient(create_app(_settings(app_db_url))) as client:
        client.post(
            "/v1/firm/kyc",
            headers=_headers(_admin),
            json={
                "rc_path": "kyc/aetoes/rc.pdf",
                "id_document_path": "kyc/aetoes/admin-id.pdf",
            },
        )
        resp = client.get("/v1/firm/kyc", headers=_headers(other_admin))
        assert resp.status_code == 404


def test_kyc_upsert_resets_to_pending(app_db_url: str) -> None:
    """A re-submit overwrites paths and resets state to PENDING (never silently
    keeps a prior verified state). There is no client path to VERIFIED — ops-only."""
    with TestClient(create_app(_settings(app_db_url))) as client:
        client.post(
            "/v1/firm/kyc",
            headers=_headers(_admin),
            json={
                "rc_path": "kyc/aetoes/rc-v1.pdf",
                "id_document_path": "kyc/aetoes/id-v1.pdf",
            },
        )

        async def _ops_verify() -> None:
            conn = await asyncpg.connect(app_db_url)
            try:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.tenant_id', $1, true)",
                        SEED_TENANT_AETOES,
                    )
                    await conn.execute(
                        "UPDATE firm_kyc SET verification_status = 'VERIFIED',"
                        " reviewed_by = 'ops', reviewed_at = now()"
                        " WHERE tenant_id = $1::uuid",
                        uuid.UUID(SEED_TENANT_AETOES),
                    )
            finally:
                await conn.close()

        asyncio.run(_ops_verify())

        resp = client.post(
            "/v1/firm/kyc",
            headers=_headers(_admin),
            json={
                "rc_path": "kyc/aetoes/rc-v2.pdf",
                "id_document_path": "kyc/aetoes/id-v2.pdf",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["kyc"]["verification_status"] == "PENDING"

        resp = client.get("/v1/firm/kyc", headers=_headers(_admin))
        assert resp.json()["kyc"]["rc_path"] == "kyc/aetoes/rc-v2.pdf"
        assert resp.json()["kyc"]["verification_status"] == "PENDING"
        assert resp.json()["kyc"]["reviewed_by"] is None

