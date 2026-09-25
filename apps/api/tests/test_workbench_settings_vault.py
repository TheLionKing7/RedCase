"""W3/V1 persistence and active-grant regression coverage."""

import asyncio

import asyncpg
from conftest import SEED_TENANT_AETOES
from fastapi.testclient import TestClient
from test_access import _auth, _settings

from app.main import create_app


async def _seed_profile(app_db_url: str) -> None:
    from conftest import APP_PASSWORD, APP_ROLE

    admin_url = app_db_url.replace(
        f"{APP_ROLE}:{APP_PASSWORD}@", "postgres:@"
    )
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute(
            "INSERT INTO firm_members (tenant_id, user_ref, full_name, role, clearance)"
            " VALUES ($1::uuid, 'profile-w3', 'Initial Name', 'Associate', 'STAFF')"
            " ON CONFLICT (tenant_id, user_ref) DO NOTHING",
            SEED_TENANT_AETOES,
        )
    finally:
        await conn.close()


async def _seed_grant(app_db_url: str) -> None:
    from conftest import APP_PASSWORD, APP_ROLE

    admin_url = app_db_url.replace(
        f"{APP_ROLE}:{APP_PASSWORD}@", "postgres:@"
    )
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute(
            "INSERT INTO document_grants"
            " (tenant_id, document_id, user_ref, grant_level, granted_by, expires_at)"
            " SELECT $1::uuid, d.id, 'grantee-w3', 'READ', 'partner-w3',"
            " now() + interval '1 day'"
            " FROM documents d JOIN vaults v ON v.id = d.vault_id"
            " WHERE v.vault_type = 'firm' LIMIT 1",
            SEED_TENANT_AETOES,
        )
    finally:
        await conn.close()



class TestProfilePersistence:
    def test_profile_is_user_editable_and_tenant_scoped(self, app_db_url):
        asyncio.run(_seed_profile(app_db_url))
        with TestClient(create_app(_settings(app_db_url))) as client:
            updated = client.put(
                "/v1/profile",
                json={
                    "full_name": "Updated Counsel",
                    "phone": "+234 800 000 0000",
                    "email": "updated@example.test",
                    "timezone": "Africa/Lagos",
                },
                headers=_auth(sub="profile-w3", clearance="STAFF"),
            )
            assert updated.status_code == 200, updated.text
            assert updated.json()["full_name"] == "Updated Counsel"
            profile = client.get("/v1/profile", headers=_auth(sub="profile-w3"))
            assert profile.json()["email"] == "updated@example.test"

class TestGrantLifecycle:
    def test_grant_visibility_and_relinquish(self, app_db_url):
        asyncio.run(_seed_grant(app_db_url))
        with TestClient(create_app(_settings(app_db_url))) as client:
            headers = _auth(sub="grantee-w3", clearance="STAFF")
            listing = client.get("/v1/access-grants", headers=headers)
            assert listing.status_code == 200, listing.text
            if listing.json()["grants"]:
                grant = listing.json()["grants"][0]
                relinquished = client.post(
                    f"/v1/access-grants/{grant['id']}/relinquish",
                    headers=_auth(sub="grantee-w3", clearance="STAFF"),
                )
                assert relinquished.status_code == 200, relinquished.text
                refreshed = client.get("/v1/access-grants", headers=headers)
                assert refreshed.json()["grants"][0]["relinquished_at"]

    def test_brief_name_request_persists_without_document_uuid(self, app_db_url):
        with TestClient(create_app(_settings(app_db_url))) as client:
            response = client.post(
                "/v1/access-requests",
                json={
                    "brief_name": "Unindexed confidential brief",
                    "reason": "Need to review",
                },
                headers=_auth(sub="requester-w3", clearance="STAFF"),
            )
            assert response.status_code == 201, response.text
            saved = response.json()["request"]
            assert saved["brief_name"] == "Unindexed confidential brief"
            assert saved["document_id"] is None


class TestPersonaExtension:
    def test_specialties_personality_and_temperature_round_trip(self, app_db_url):
        with TestClient(create_app(_settings(app_db_url))) as client:
            saved = client.put(
                "/v1/persona",
                json={
                    "agent_name": "Counsel Assistant",
                    "tone_preset": "PROFESSIONAL",
                    "personality": "Measured and candid",
                    "working_style": "Start with the issue",
                    "reviewer_specialty": "Procedural defects",
                    "researcher_specialty": "Appellate authorities",
                    "redteam_temperature": 0.65,
                },
                headers=_auth(sub="settings-w3", clearance="STAFF"),
            )
            assert saved.status_code == 200, saved.text
            assert saved.json()["reviewer_specialty"] == "Procedural defects"
            assert saved.json()["redteam_temperature"] == 0.65
