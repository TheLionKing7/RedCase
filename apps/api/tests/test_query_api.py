"""POST /v1/query API tests + Supabase JWT verification units — Tasks 1.4/1.5.

Auth contract under test (owner ruling 3, 2026-09-16): Supabase Auth magic
link issues a JWT signed with the project's shared JWT secret; FastAPI
verifies it (HS256, signature, exp, alg), takes user_ref from ``sub`` and
tenant_id from ``app_metadata.tenant_id``, and opens an RLS-scoped connection.
A token missing either claim is rejected — tenant scoping is never guessed.

Settings in every test are built with ``_env_file=None`` so the developer's
real ``.env`` (Supabase pooler DSN, live API keys) can never leak into a
test run; the e2e tests point at the embedded Postgres session fixture only.
"""

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

import app.retrieval.service as service_module
from app.config import Settings
from app.deps import JwtError, verify_supabase_jwt
from app.ingestion.db import EMBEDDING_DIMS, ingest_pdf
from app.main import create_app
from tests.pdf_factory import make_pdf, synthetic_judgment_pages

VAULT_JURIS_NG = uuid.UUID("b0000001-0000-4000-8000-000000000001")
JWT_SECRET = "test-jwt-secret-not-a-real-secret"  # noqa: S105 (throwaway test secret)
QUESTION = "What is the ratio on statutory interpretation of constitutional questions?"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def make_jwt(
    secret: str = JWT_SECRET,
    *,
    sub: str = "user-1",
    tenant: str | None = SEED_TENANT_AETOES,
    exp_offset: int = 3600,
    alg: str = "HS256",
) -> str:
    header = {"alg": alg, "typ": "JWT"}
    payload: dict = {"sub": sub, "exp": int(time.time()) + exp_offset}
    if tenant is not None:
        payload["app_metadata"] = {"tenant_id": tenant}
    seg = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(payload).encode())}"
    sig = hmac.new(secret.encode(), seg.encode(), hashlib.sha256).digest()
    return f"{seg}.{_b64url(sig)}"


class ConstantEmbedder:
    def __init__(self, value: float = 0.5) -> None:
        self.value = value

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[self.value] * EMBEDDING_DIMS for _ in texts]


class FarEmbedder(ConstantEmbedder):
    def __init__(self) -> None:
        super().__init__(-1.0)


class GoodLLM:
    async def answer(self, system: str, user: str) -> str:
        import re

        m = re.search(r'<passage doc_id="([^"]+)"', user)
        return (
            "Per the retrieved passage, the holding is settled. "
            f'<citations>doc_id="{m.group(1)}"</citations>'
        )


async def _ingest(app_db_url: str, tmp_path) -> None:
    n = int(uuid.uuid4().hex[:6], 16)
    citation = f"(2005) {1 + n % 9} NWLR (Pt. {180 + n % 600}) {1 + n % 400}"
    pages = synthetic_judgment_pages()
    pages[0] = [citation if "NWLR CITATION" in line else line for line in pages[0]]
    pdf = make_pdf(tmp_path / f"api-{n}.pdf", pages)
    conn = await asyncpg.connect(app_db_url)
    try:
        await ingest_pdf(
            conn,
            tenant_id=uuid.UUID(SEED_TENANT_AETOES),
            vault_id=VAULT_JURIS_NG,
            pdf_path=pdf,
            embedder=ConstantEmbedder(),
        )
    finally:
        await conn.close()


class TestVerifySupabaseJwt:
    def test_roundtrip(self) -> None:
        claims = verify_supabase_jwt(make_jwt(), JWT_SECRET)
        assert claims["sub"] == "user-1"
        assert claims["app_metadata"]["tenant_id"] == SEED_TENANT_AETOES

    def test_bad_signature_rejected(self) -> None:
        with pytest.raises(JwtError):
            verify_supabase_jwt(make_jwt(), "wrong-secret")

    def test_expired_rejected(self) -> None:
        with pytest.raises(JwtError, match="expired"):
            verify_supabase_jwt(make_jwt(exp_offset=-10), JWT_SECRET)

    def test_wrong_alg_rejected(self) -> None:
        # alg=none tokens are the classic bypass; only HS256 is accepted.
        with pytest.raises(JwtError, match="alg"):
            verify_supabase_jwt(make_jwt(alg="none"), JWT_SECRET)

    def test_malformed_rejected(self) -> None:
        with pytest.raises(JwtError, match="malformed"):
            verify_supabase_jwt("not-a-jwt", JWT_SECRET)


class TestQueryEndpointAuth:
    def _client(self, **settings_kwargs) -> TestClient:
        kwargs = {"_env_file": None, **settings_kwargs}
        return TestClient(create_app(Settings(**kwargs)))

    def test_401_without_bearer(self) -> None:
        with self._client(supabase_jwt_secret=JWT_SECRET) as client:
            resp = client.post("/v1/query", json={"question": QUESTION})
            assert resp.status_code == 401

    def test_503_bearer_but_no_jwt_secret_provisioned(self) -> None:
        with self._client() as client:
            resp = client.post(
                "/v1/query",
                json={"question": QUESTION},
                headers={"Authorization": f"Bearer {make_jwt()}"},
            )
            assert resp.status_code == 503

    def test_401_bad_signature(self) -> None:
        bad = make_jwt(secret="other")  # noqa: S106 (test token, not a credential)
        with self._client(supabase_jwt_secret=JWT_SECRET) as client:
            resp = client.post(
                "/v1/query",
                json={"question": QUESTION},
                headers={"Authorization": f"Bearer {bad}"},
            )
            assert resp.status_code == 401

    def test_401_missing_tenant_claim(self) -> None:
        with self._client(supabase_jwt_secret=JWT_SECRET) as client:
            resp = client.post(
                "/v1/query",
                json={"question": QUESTION},
                headers={"Authorization": f"Bearer {make_jwt(tenant=None)}"},
            )
            assert resp.status_code == 401
            assert "tenant" in resp.json()["detail"]

    def test_503_valid_jwt_but_no_database(self) -> None:
        with self._client(supabase_jwt_secret=JWT_SECRET) as client:
            resp = client.post(
                "/v1/query",
                json={"question": QUESTION},
                headers={"Authorization": f"Bearer {make_jwt()}"},
            )
            assert resp.status_code == 503


class TestQueryEndpointE2E:
    def _settings(self, app_db_url: str) -> Settings:
        return Settings(
            _env_file=None,
            database_url=app_db_url,
            supabase_jwt_secret=JWT_SECRET,
        )

    def test_200_grounded_answer_with_citations(
        self, app_db_url: str, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio

        asyncio.run(_ingest(app_db_url, tmp_path))
        monkeypatch.setattr(
            service_module, "make_embedder", lambda s: ConstantEmbedder()
        )
        monkeypatch.setattr(service_module, "make_llm", lambda s: GoodLLM())
        with TestClient(create_app(self._settings(app_db_url))) as client:
            resp = client.post(
                "/v1/query",
                json={"question": QUESTION},
                headers={"Authorization": f"Bearer {make_jwt()}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["refusal"] is False
        assert len(body["citations"]) == 1
        cite = body["citations"][0]
        assert cite["verified"] is True
        assert cite["court_level"] == "SUPREME_COURT"
        assert cite["page_start"] >= 1
        assert set(cite) == {
            "document_id", "case_title", "citation", "court_level", "year",
            "page_start", "page_end", "paragraph_refs", "source_pdf_url",
            "verified",
        }  # §3.5 Citation wire shape, exact

    def test_200_refusal_when_below_threshold(
        self, app_db_url: str, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import asyncio

        asyncio.run(_ingest(app_db_url, tmp_path))
        monkeypatch.setattr(service_module, "make_embedder", lambda s: FarEmbedder())
        monkeypatch.setattr(service_module, "make_llm", lambda s: GoodLLM())
        with TestClient(create_app(self._settings(app_db_url))) as client:
            resp = client.post(
                "/v1/query",
                json={"question": QUESTION, "year_from": 2020, "year_to": 2026},
                headers={"Authorization": f"Bearer {make_jwt()}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["refusal"] is True
        assert body["citations"] == []

    def test_422_invalid_body(self, app_db_url: str) -> None:
        with TestClient(create_app(self._settings(app_db_url))) as client:
            resp = client.post(
                "/v1/query",
                json={"question": "short"},  # §3.5 min_length=10
                headers={"Authorization": f"Bearer {make_jwt()}"},
            )
        assert resp.status_code == 422
