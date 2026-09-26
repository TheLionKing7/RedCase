"""Task 2.3 DoD — Vault A ingestion endpoint tests (owner brief 2026-09-19).

DoD items:
  (a) endpoint-level write authorization — staff ingesting PARTNER_RESTRICTED
      or naming grantees beyond their authority are rejected at the API;
  (b) hash idempotency — re-ingesting identical bytes is a no-op;
  (c) enc:v1 round-trip inversion — an authorized read returns plaintext
      while the stored row remains ciphertext;
  plus the ruling-1 defaults: CONFIDENTIAL default classification, PR
      requires named grantees, default ACL = uploader + named individuals.

Synthetic PDFs only (pdf_factory). The retrieval-side pen-test regime
from 2.2 is re-run against these endpoints here: reads below clearance
return 404 (RLS), not leaked content.
"""

import base64
import hashlib
import hmac
import json
import time
import uuid
from io import BytesIO
from zipfile import ZipFile

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient

import app.routers.vault_a as vault_a_module
from app.config import Settings
from app.main import create_app
from app.vault_a.crypto import PREFIX, make_key_provider
from tests.pdf_factory import make_pdf, synthetic_judgment_pages

JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105
MASTER_KEY_HEX = "cd" * 32  # throwaway test master key (dev provider)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_jwt(
    *, sub: str = "uploader-1", clearance: str = "STAFF",
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


class ConstantEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.25] * 1024 for _ in texts]


@pytest.fixture
def client(app_db_url: str, monkeypatch: pytest.MonkeyPatch):
    settings = Settings(
        database_url=app_db_url,
        supabase_jwt_secret=JWT_SECRET,
        vault_a_key_provider="local",
        vault_a_master_key=MASTER_KEY_HEX,
    )
    monkeypatch.setattr(
        vault_a_module, "make_embedder", lambda s: ConstantEmbedder()
    )
    monkeypatch.setattr(
        vault_a_module, "make_key_provider", lambda s: make_key_provider(settings)
    )
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
async def matter_id(app_db_url: str) -> uuid.UUID:
    """A synthetic matter under a synthetic client (partner-scoped setup)."""
    conn = await asyncpg.connect(app_db_url)
    try:
        tenant = SEED_TENANT_AETOES
        client_id, matter = uuid.uuid4(), uuid.uuid4()
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO vaults (id, tenant_id, vault_type, name, is_shared)"
                " VALUES ($1, $2, 'firm', $3, FALSE)",
                uuid.uuid4(), tenant,
                f"Intake Firm Vault {uuid.uuid4().hex[:8]}",
            )
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
                client_id, tenant, f"Intake Test Client {uuid.uuid4().hex[:8]}",
            )
            await conn.execute(
                "INSERT INTO matters (id, tenant_id, client_id, matter_ref)"
                " VALUES ($1, $2, $3, $4)",
                matter, tenant, client_id,
                f"INTAKE-{uuid.uuid4().hex[:8]} v. Syn",
            )
        return matter
    finally:
        await conn.close()


def _pdf_bytes(tmp_path, marker: str) -> bytes:
    return make_pdf(
        tmp_path / f"intake-{marker}.pdf", synthetic_judgment_pages()
    ).read_bytes()


def _post(client, matter, token, raw, *, content_type="application/pdf", **params):
    return client.post(
        f"/v1/matters/{matter}/documents",
        params={k: v for k, v in params.items() if v is not None},
        content=raw,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": content_type},
    )


class TestRuling1Defaults:
    def test_default_classification_is_confidential(
        self, client, matter_id, tmp_path
    ) -> None:
        raw = _pdf_bytes(tmp_path, "defclass")
        resp = _post(client, matter_id, make_jwt(), raw, title="memo.pdf")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["duplicate"] is False
        assert body["classification_level"] == "CONFIDENTIAL"

    def test_uploader_in_default_acl_can_read_back(
        self, client, matter_id, tmp_path
    ) -> None:
        token = make_jwt(sub="up-reader", clearance="STAFF")
        raw = _pdf_bytes(tmp_path, "readback")
        doc_id = _post(client, matter_id, token, raw).json()["document_id"]
        got = client.get(
            f"/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert got.status_code == 200, got.text
        assert any("synthetic" in c["text"] or len(c["text"]) > 0
                   for c in got.json()["chunks"])


class TestWriteAuthorization:
    def test_staff_pr_ingest_rejected(
        self, client, matter_id, tmp_path
    ) -> None:
        raw = _pdf_bytes(tmp_path, "staffpr")
        resp = _post(
            client, matter_id, make_jwt(clearance="STAFF"), raw,
            classification="PARTNER_RESTRICTED", grantees="u-x",
        )
        assert resp.status_code == 403

    def test_staff_naming_grantees_rejected(
        self, client, matter_id, tmp_path
    ) -> None:
        raw = _pdf_bytes(tmp_path, "staffgrant")
        resp = _post(
            client, matter_id, make_jwt(clearance="STAFF"), raw,
            grantees="colleague-1",
        )
        assert resp.status_code == 403

    def test_pr_requires_named_grantees(
        self, client, matter_id, tmp_path
    ) -> None:
        token = make_jwt(clearance="PARTNER")
        raw = _pdf_bytes(tmp_path, "prnograntee")
        resp = _post(
            client, matter_id, token, raw, classification="PARTNER_RESTRICTED"
        )
        assert resp.status_code == 422

    def test_pr_rejects_class_level_grantees(
        self, client, matter_id, tmp_path
    ) -> None:
        token = make_jwt(clearance="PARTNER")
        raw = _pdf_bytes(tmp_path, "prclassgrant")
        resp = _post(
            client, matter_id, token, raw,
            classification="PARTNER_RESTRICTED", grantees="all partners",
        )
        assert resp.status_code == 403

    def test_pr_named_grantees_default_acl_is_exact(
        self, client, matter_id, tmp_path, app_db_url
    ) -> None:
        token = make_jwt(sub="pr-uploader", clearance="PARTNER")
        raw = _pdf_bytes(tmp_path, "prnamed")
        resp = _post(
            client, matter_id, token, raw,
            classification="PARTNER_RESTRICTED", grantees="named-1,named-2",
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()["document_id"]
        # The default ACL holds exactly the uploader + the two named
        # individuals — no partner-class row exists to re-defeat the
        # grant-gated ruling.
        async def _grants():
            conn = await asyncpg.connect(app_db_url)
            try:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.tenant_id', $1, true)",
                        SEED_TENANT_AETOES,
                    )
                    return await conn.fetch(
                        "SELECT user_ref FROM document_grants"
                        " WHERE document_id = $1 ORDER BY user_ref",
                        uuid.UUID(doc_id),
                    )
            finally:
                await conn.close()

        grantees = [r["user_ref"] for r in pytest.importorskip("asyncio").run(_grants())]
        assert grantees == ["named-1", "named-2", "pr-uploader"]


class TestIdempotency:
    def test_reingest_identical_bytes_is_noop(
        self, client, matter_id, tmp_path
    ) -> None:
        raw = _pdf_bytes(tmp_path, "idem")
        token = make_jwt()
        first = _post(client, matter_id, token, raw)
        second = _post(client, matter_id, token, raw)
        assert first.status_code == 200 and second.status_code == 200
        assert second.json()["duplicate"] is True
        assert second.json()["document_id"] == first.json()["document_id"]
        assert second.json()["chunks"] == 0

    def test_different_bytes_new_document(
        self, client, matter_id, tmp_path
    ) -> None:
        token = make_jwt()
        one = _post(client, matter_id, token, _pdf_bytes(tmp_path, "a1"))
        two = _post(client, matter_id, token, _pdf_bytes(tmp_path, "a2"))
        assert one.json()["document_id"] != two.json()["document_id"]

    def test_docx_reingest_uses_original_upload_bytes_for_dedup(
        self, client, matter_id
    ) -> None:
        raw = _docx_bytes("DOCX intake text with a distinctive paragraph.")
        token = make_jwt()
        first = _post(
            client, matter_id, token, raw, title="brief.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        second = _post(
            client, matter_id, token, raw, title="brief.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert second.json()["duplicate"] is True
        assert second.json()["document_id"] == first.json()["document_id"]
        assert second.json()["chunks"] == 0
        readback = client.get(
            f"/v1/documents/{first.json()['document_id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert readback.status_code == 200
        assert any(
            "DOCX intake text" in chunk["text"]
            for chunk in readback.json()["chunks"]
        )

    def test_docx_invalid_archive_is_rejected(self, client, matter_id) -> None:
        response = _post(
            client, matter_id, make_jwt(), b"not a zip file",
            title="corrupt.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        assert response.status_code == 422


def _docx_bytes(paragraph: str) -> bytes:
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>' + paragraph + '</w:t></w:r></w:p></w:body></w:document>'
    )
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return stream.getvalue()


class TestEncryptedRoundTripInversion:
    def test_authorized_read_plaintext_stored_row_ciphertext(
        self, client, matter_id, tmp_path, app_db_url
    ) -> None:
        token = make_jwt(sub="enc-reader", clearance="STAFF")
        raw = _pdf_bytes(tmp_path, "encrt")
        doc_id = _post(client, matter_id, token, raw).json()["document_id"]

        got = client.get(
            f"/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert got.status_code == 200
        plaintext_chunks = [c["text"] for c in got.json()["chunks"]]
        assert any(len(t) > 0 for t in plaintext_chunks)
        assert not any(t.startswith(PREFIX) for t in plaintext_chunks)

        # The STORED row is ciphertext (default classification is
        # CONFIDENTIAL -> encrypted).
        async def _stored():
            conn = await asyncpg.connect(app_db_url)
            try:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.tenant_id', $1, true)",
                        SEED_TENANT_AETOES,
                    )
                    await conn.execute(
                        "SELECT set_config('app.user_clearance', 'PARTNER', true)"
                    )
                    await conn.execute(
                        "SELECT set_config('app.user_ref', 'audit-partner', true)"
                    )
                    return await conn.fetchval(
                        "SELECT chunk_text FROM document_chunks"
                        " WHERE document_id = $1 LIMIT 1",
                        uuid.UUID(doc_id),
                    )
            finally:
                await conn.close()

        stored = pytest.importorskip("asyncio").run(_stored())
        assert stored.startswith(PREFIX)

    def test_unauthorized_read_is_404_not_a_leak(
        self, client, matter_id, tmp_path
    ) -> None:
        owner = make_jwt(sub="enc-owner", clearance="STAFF")
        doc_id = _post(
            client, matter_id, owner, _pdf_bytes(tmp_path, "noleak")
        ).json()["document_id"]
        stranger = make_jwt(sub="stranger-staff", clearance="STAFF")
        got = client.get(
            f"/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {stranger}"},
        )
        assert got.status_code == 404
