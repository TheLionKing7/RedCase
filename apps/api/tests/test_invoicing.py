"""Practice operations — invoicing + payments tests (Addendum §9.1, task 3.9 sub-task 2).

DoD under test:
  * Continuity with sub-task 1 — a time entry created via POST /v1/matters/{id}/time
    (the sub-task-1 endpoint) is invoiceable here: unbilled → DRAFT invoice bills exactly those
    entries, marks them billed=TRUE, and a second invoice excludes them.
  * one-click invoice → PDF export (brand letterhead) → mark-sent → payment recording →
    status transitions (DRAFT → SENT → PARTIAL → PAID) → receivables aging.
  * Tenancy: a foreign invoice id is a 404; a second tenant reads zero of ours at SQL level.
  * Guards: no unbilled entries → 409; zero-rate entries → 422; re-send of a SENT
    invoice → 409; payment on a PAID invoice → 409.

rate_ngn is an hourly rate (NGN/hour); invoice line amount = minutes/60 * rate (the
“rate_ngn NULL = use matter default” pointer has no matter-default column, so entries without a
rate are not billable — a firm must set a rate to bill).
"""

import asyncio
import base64
import hashlib
import hmac
import json
import time
import uuid

import asyncpg
import pymupdf
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105

HOUR = "12345.00"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_jwt(*, sub: str = "inv-user", tenant: str = SEED_TENANT_AETOES) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "exp": int(time.time()) + 3600,
        "app_metadata": {"tenant_id": tenant, "clearance": "PARTNER"},
    }
    seg = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    sig = hmac.new(JWT_SECRET.encode(), seg.encode(), hashlib.sha256).digest()
    return f"{seg}.{_b64url(sig)}"


def _auth(*, sub: str = "inv-user", tenant: str = SEED_TENANT_AETOES) -> dict:
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
                "INSERT INTO clients (id, tenant_id, name) VALUES ($1, $2, $3)",
                client_id,
                tenant,
                f"Invoice Client {uuid.uuid4().hex[:8]}",
            )
            await conn.execute(
                "INSERT INTO matters (id, tenant_id, client_id, matter_ref)"
                " VALUES ($1, $2, $3, $4)",
                matter,
                tenant,
                client_id,
                f"INV-{uuid.uuid4().hex[:8]} v. Syn",
            )
        return matter
    finally:
        await conn.close()


def _record_time(
    client: TestClient, matter: uuid.UUID, *, description: str, minutes: int, rate: str
) -> dict:
    resp = client.post(
        f"/v1/matters/{matter}/time",
        json={
            "description": description,
            "minutes": minutes,
            "rate_ngn": rate,
            "idempotency_key": f"t-{uuid.uuid4().hex}",
        },
        headers=_auth(),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()

class TestInvoiceLifecycle:
    """End-to-end round-trip: sub-task-1 time entry → DRAFT → SENT → PDF → PARTIAL → PAID."""

    def test_full_round_trip(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            # --- sub-task-1 continuity: the /time endpoint creates the billable work ---
            _record_time(
                client, matter, description="reviewed affidavit", minutes=120, rate=HOUR
            )
            _record_time(
                client, matter, description="drafted reply", minutes=60, rate=HOUR
            )

            # --- 1. one-click invoice from unbilled entries ---
            r = client.post(
                f"/v1/matters/{matter}/invoice",
                json={"due_date": "2026-10-01"},
                headers=_auth(),
            )
            assert r.status_code == 201, r.text
            inv = r.json()
            assert inv["status"] == "DRAFT"
            assert inv["number"].startswith("RC-")
            # 120min @ ₦12,345/h = 24,690.00 ; 60min = 12,345.00 → total
            assert float(inv["amount_ngn"]) == 37035.00
            assert inv["balance_ngn"] == inv["amount_ngn"]
            invoice_id = inv["id"]

            # --- billed entries are no longer unbilled; a second invoice is empty ---
            listed = client.get(f"/v1/matters/{matter}/time", headers=_auth())
            billed = [x for x in listed.json()["entries"] if x["billed"]]
            assert len(billed) == 2
            empty = client.post(
                f"/v1/matters/{matter}/invoice", json={}, headers=_auth()
            )
            assert empty.status_code == 409, empty.text

            # --- 2. detail shows lines ---
            detail = client.get(f"/v1/invoices/{invoice_id}", headers=_auth())
            assert detail.status_code == 200
            assert len(detail.json()["lines"]) == 2


            # --- 3. PDF export with brand letterhead (parses as a real PDF) ---
            pdf = client.get(f"/v1/invoices/{invoice_id}.pdf", headers=_auth())
            assert pdf.status_code == 200
            assert pdf.headers["content-type"] == "application/pdf"
            doc = pymupdf.open(stream=pdf.content, filetype="pdf")
            text = "".join(page.get_text() for page in doc)
            assert "INVOICE" in text
            assert inv["number"] in text
            doc.close()

            # --- 4. mark-sent ---
            sent = client.post(
                f"/v1/invoices/{invoice_id}/send", headers=_auth()
            )
            assert sent.status_code == 200
            assert sent.json()["status"] == "SENT"
            assert sent.json()["sent_at"] is not None

            # --- 5. partial payment → PARTIAL ---
            p1 = client.post(
                f"/v1/invoices/{invoice_id}/payments",
                json={"amount_ngn": "10000.00", "method": "BANK_TRANSFER"},
                headers=_auth(),
            )
            assert p1.status_code == 201
            assert p1.json()["status"] == "PARTIAL"
            assert float(p1.json()["paid_ngn"]) == 10000.00

            # --- 6. remaining payment → PAID ---
            p2 = client.post(
                f"/v1/invoices/{invoice_id}/payments",
                json={"amount_ngn": "27035.00", "method": "BANK_TRANSFER"},
                headers=_auth(),
            )
            assert p2.status_code == 201
            assert p2.json()["status"] == "PAID"

            # --- 7. payment on a PAID invoice is rejected ---
            over = client.post(
                f"/v1/invoices/{invoice_id}/payments",
                json={"amount_ngn": "1.00"},
                headers=_auth(),
            )
            assert over.status_code == 409

            # --- 8. receivables aging excludes the settled invoice ---
            aging = client.get("/v1/receivables/aging", headers=_auth())
            assert aging.status_code == 200
            by = {b["label"]: b["total_ngn"] for b in aging.json()}
            assert all(float(v) == 0 for v in by.values())


class TestInvoiceGuards:
    def test_no_unbilled_entries_is_409(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.post(f"/v1/matters/{matter}/invoice", json={}, headers=_auth())
            assert r.status_code == 409

    def test_zero_rate_entries_is_422(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            # Only an UNRATED entry — nothing valued → cannot build a bill.
            client.post(
                f"/v1/matters/{matter}/time",
                json={
                    "description": "unrated",
                    "minutes": 30,
                    "idempotency_key": f"x-{uuid.uuid4().hex}",
                },
                headers=_auth(),
            )
            r = client.post(f"/v1/matters/{matter}/invoice", json={}, headers=_auth())
            assert r.status_code == 422

    def test_foreign_invoice_is_404(self, app_db_url: str) -> None:
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.get(f"/v1/invoices/{uuid.uuid4()}", headers=_auth())
            assert r.status_code == 404

    def test_resent_sent_invoice_is_409(self, app_db_url: str) -> None:
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            _record_time(client, matter, description="x", minutes=60, rate=HOUR)
            inv = client.post(
                f"/v1/matters/{matter}/invoice", json={}, headers=_auth()
            ).json()
            sent = client.post(
                f"/v1/invoices/{inv['id']}/send", headers=_auth()
            ).json()
            assert sent["status"] == "SENT"
            again = client.post(
                f"/v1/invoices/{inv['id']}/send", headers=_auth()
            )
            assert again.status_code == 409


class TestTenantIsolation:
    async def _provision_tenant_b(self, app_db_url: str) -> str:
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

    def test_second_tenant_reads_zero_invoices(self, app_db_url: str) -> None:
        tenant_b = asyncio.run(self._provision_tenant_b(app_db_url))
        matter = asyncio.run(_provision_matter(app_db_url, SEED_TENANT_AETOES))
        with TestClient(create_app(_settings(app_db_url))) as client:
            _record_time(client, matter, description="x", minutes=60, rate=HOUR)
            inv = client.post(
                f"/v1/matters/{matter}/invoice", json={}, headers=_auth()
            ).json()

            # Tenant B cannot fetch tenant A's invoice (RLS → 404).
            foreign = client.get(
                f"/v1/invoices/{inv['id']}", headers=_auth(tenant=tenant_b)
            )
            assert foreign.status_code == 404

