"""Shared test fixtures — embedded PostgreSQL (pgvector) per test session.

RLS caveat: superusers bypass row-level security entirely, so the app-level
connection used in tests is a NON-superuser role (``redcase_app``). The
migration runs as the cluster owner (needed to create DDL); grants are then
issued so the app role exercises real policy enforcement.
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
import pgserver
import pytest

API_DIR = Path(__file__).resolve().parents[1]

APP_ROLE = "redcase_app"
APP_PASSWORD = "testpass"  # noqa: S105 (throwaway embedded-test cluster only)
APP_DB = "redcase_test"
SEED_TENANT_AETOES = "a0000001-0000-4000-8000-000000000001"

# Live-LLM / network-dependent suites (citation battery, retrieval chain, route-set
# accuracy) must NEVER hard-fail in CI or on a machine without reachable providers.
# They are opt-in: they only RUN when RUN_LIVE_TESTS=1 is explicitly set. When
# unset they skip regardless of whether provider keys happen to be present in the
# environment — presence of a key is not proof the network/provider is reachable, and a
# green "N passed" signal must never be noise from timeouts (HANDOFF §4 quality gate).


def live_tests_enabled() -> tuple[bool, str]:
    """True only when the operator has explicitly opted into live provider tests."""
    flag = os.environ.get("RUN_LIVE_TESTS", "")
    if flag != "1":
        return False, "set RUN_LIVE_TESTS=1 to run live provider/network tests"
    return True, ""


def live_tests_gate() -> object:
    """pytest.mark.skipif marker factory for live suites (single consistent gate)."""
    ok, reason = live_tests_enabled()
    return pytest.mark.skipif(not ok, reason=f"live tests disabled: {reason}")


@pytest.fixture(scope="session")
def app_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    data_dir = tmp_path_factory.mktemp("pgdata")
    srv = pgserver.get_server(str(data_dir))
    parsed = urlparse(srv.get_uri())

    # Fresh database + non-superuser app role (RLS must actually apply).
    # Note: PG16 creates session placeholder GUCs only via set_config()
    # (ALTER SYSTEM/SET on unknown dotted names error out) — HANDOFF.md 2.2
    # contract is SET LOCAL semantics per transaction, which set_config(...,
    # is_local=true) provides.
    srv.psql(f"CREATE DATABASE {APP_DB}")
    srv.psql(f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}' NOSUPERUSER")

    # Run the real migration chain against a fresh DB (DoD: applies clean).
    admin_url = srv.get_uri(database=APP_DB)
    env = {**os.environ, "DATABASE_URL": admin_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=API_DIR,
        env=env,
        check=True,
        capture_output=True,
    )

    # Grants for the app role (schema + tables created by the owner role).
    async def _grant() -> None:
        conn = await asyncpg.connect(admin_url)
        try:
            await conn.execute(f"GRANT CONNECT ON DATABASE {APP_DB} TO {APP_ROLE}")
            await conn.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
            await conn.execute(
                "GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public "
                f"TO {APP_ROLE}"
            )
            # Append-only tables (HANDOFF.md 3): UPDATE/DELETE revoked from the
            # app role — audit immutability is a database grant, not a promise.
            await conn.execute(f"REVOKE UPDATE, DELETE ON query_audit FROM {APP_ROLE}")
            await conn.execute(
                f"REVOKE UPDATE, DELETE ON entitlement_events FROM {APP_ROLE}"
            )
            # signup_audit is the provisioning log — same append-only contract
            # (documented in migration 0018). Immutability is a DB grant.
            await conn.execute(f"REVOKE UPDATE, DELETE ON signup_audit FROM {APP_ROLE}")
            await conn.execute(
                "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public "
                f"TO {APP_ROLE}"
            )
        finally:
            await conn.close()

    import asyncio

    asyncio.run(_grant())

    yield f"postgresql://{APP_ROLE}:{APP_PASSWORD}@{parsed.hostname}:{parsed.port}/{APP_DB}"

    srv.cleanup()
