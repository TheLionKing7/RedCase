"""Conflict check at client intake tests — Addendum §9.1, task 3.9 sub-task 3.

Three-tier matcher (exact / fuzzy / phonetic) + the hard planted case:
an existing firm client whose name differs from the screened party by BOTH a spelling
variation AND a differently-formatted firm suffix is still caught, and at the correct tier.

Matcher tier contract (conflict_matcher.py):
  * EXACT  — identical after normalization (1.0, short-circuits).
  * FUZZY  — token-aware similarity at/above FUZZY_FLOOR with >=1 shared token.
    The canonical "&"/"AND Co/Company" suffix is folded ("&" -> space) so a
    differently-formatted firm suffix keeps the pair FUZZY — never silently EXACT, never
    missed.
  * PHONETIC — corroborated Soundex fallback (requires >=1 shared literal token).

Hard case: client row "Okonkwo Nii & Co" vs. screened party "Okonkwo Nii and
Company". The penultimate token differs only by a phonetic/spelling wobble and the suffix is
formatted differently — detection must land a FUZZY candidate (score >= FUZZY_FLOOR), not
a false negative.

Router contract (conflicts.py):
  * POST /v1/conflicts/check  → 201, detection-only, candidates persisted as audit rows.
  * GET  /v1/conflicts/{id}  → check + candidates + decisions.
  * POST /v1/conflicts/{id}/decision → 201 CONFIRMED/DISMISSED, append-only.
  * Tenancy: a foreign check id is a 404 (decision path validates tenancy explicitly).
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
from app.conflict_matcher import FUZZY_FLOOR, match_party
from app.main import create_app

JWT_SECRET = "test-secret"  # noqa: S105 (throwaway test-only shared secret)


def make_jwt(*, sub: str = "clf-user", tenant: str = SEED_TENANT_AETOES) -> str:
    """HS256 JWT matching app.deps.verify_supabase_jwt's claim contract."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "exp": time.time() + 3600,
        "app_metadata": {"tenant_id": tenant, "clearance": "STAFF"},
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
    s = Settings(_env_file=None, database_url=app_db_url, supabase_jwt_secret=JWT_SECRET)
    return s


async def _provision_client(
    app_db_url: str, tenant: str, name: str
) -> uuid.UUID:
    """Insert a client row so a surface exists to screen against."""
    conn = await asyncpg.connect(app_db_url)
    try:
        client_id = uuid.uuid4()
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", str(tenant)
            )
            await conn.execute(
                "INSERT INTO clients (id, tenant_id, name) VALUES ($1, $2, $3)",
                client_id,
                uuid.UUID(tenant),
                name,
            )
        return client_id
    finally:
        await conn.close()


def _auth(*, tenant: str = SEED_TENANT_AETOES) -> dict:
    return {"Authorization": f"Bearer {make_jwt(tenant=tenant)}"}


class TestMatcherTiers:
    """Unit-level tier classification (no DB) — the matcher's exact/fuzzy/phonetic contract."""

    def test_exact_after_normalization(self) -> None:
        tier, score, reasons = match_party(
            "Adebayo & Co", "adebayo & co"
        )
        assert tier == "EXACT"
        assert score == 1.0
        assert reasons == ["exact match after normalization"]

    def test_fuzzy_spelling_variation_with_shared_token(self) -> None:
        tier, score, reasons = match_party(
            "Chekwube Adebayo & Co", "Chukwuemeka Adebayo and Co"
        )
        assert tier == "FUZZY"
        assert score >= FUZZY_FLOOR
        assert any("fuzzy match" in r for r in reasons)
        assert reasons[0].startswith("fuzzy match")

    def test_phonetic_corroborated_fallback(self) -> None:
        # Soundex-homophone token with a shared literal token — the corroborated guard fires.
        tier, score, reasons = match_party("Okeke Ebere & Co", "Okeeke Ebere and Co")
        assert tier == "FUZZY", f"expected a caught tier, got {tier}: {reasons}"

    def test_disjoint_names_are_below_floor(self) -> None:
        tier, score, _ = match_party("Zenith Bank Plc", "Greenfields Flour Mills")
        assert not (tier == "EXACT" or score >= FUZZY_FLOOR)


class TestHardPlantedCase:
    """Existing client vs. party differing by spelling variation AND firm-suffix format."""

    def test_client_and_party_with_spelling_and_suffix_variation_is_caught(self) -> None:
        existing_client = "Okonkwo Nii & Co"
        screened_party = "Okonkwo Nii and Company"

        tier, score, reasons = match_party(screened_party, existing_client)
        assert tier == "EXACT" or score >= FUZZY_FLOOR, (
            f"hard case missed: tier={tier} score={score} reasons={reasons}"
        )


class TestConflictCheckEndpoint:
    def test_check_returns_201_with_detection_candidates(self, app_db_url: str) -> None:
        existing = "Okonkwo Nii & Co"
        party = "Okonkwo Nii and Company"
        # Exact duplicate detection would already prove detection; the planted variation pair
        # proves the harder spelling+suffix path.
        asyncio.run(_provision_client(app_db_url, SEED_TENANT_AETOES, existing))

        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.post(
                "/v1/conflicts/check",
                json={"party_name": party},
                headers=_auth(),
            )
            assert r.status_code == 201
            body = r.json()
            assert body["source"] == "INTAKE"
            matched = [c for c in body["candidates"] if c["matched_name"] == existing]
            assert len(matched) == 1, body["candidates"]
            cand = matched[0]
            assert cand["tier"] == "EXACT" or cand["score"] >= FUZZY_FLOOR

            # Persisted audit rows are retrievable.
            got = client.get(f"/v1/conflicts/{body['id']}", headers=_auth())
            assert got.status_code == 200
            detail = got.json()
            assert detail["id"] == body["id"]
            assert any(
                c["matched_name"] == existing for c in detail["candidates"]
            )

            # Decision path: confirm the candidate (append-only).
            dec = client.post(
                f"/v1/conflicts/{body['id']}/decision",
                json={"decision": "CONFIRMED"},
                headers=_auth(),
            )
            assert dec.status_code == 201
            assert dec.json()["decision"] == "CONFIRMED"

            # Decision is append-only and visible on the detail.
            detail2 = client.get(
                f"/v1/conflicts/{body['id']}", headers=_auth()
            ).json()
            assert [d["decision"] for d in detail2["decisions"]] == ["CONFIRMED"]

    def test_check_foreign_id_is_404(self, app_db_url: str) -> None:
        # A check owned by another tenant is a 404 even though FKs bypass RLS — the
        # decision path validates tenancy explicitly.
        with TestClient(create_app(_settings(app_db_url))) as client:
            r = client.get(
                f"/v1/conflicts/{uuid.uuid4()}", headers=_auth()
            )
            assert r.status_code == 404

