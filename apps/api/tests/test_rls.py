"""Row-Level Security policy tests — Task 1.2 DoD (Phase1-Design §2.1).

Contract under test (HANDOFF.md §2.2, §2.5):
  * every query runs with ``app.tenant_id`` set via SET LOCAL;
  * policies live in SQL, not Python;
  * the policy uses ``current_setting('app.tenant_id')`` with NO default, so a
    connection without the GUC fails closed instead of seeing everything.
"""

import uuid

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES

VAULT_JURIS_NG = "b0000001-0000-4000-8000-000000000001"

INSERT_DOC = """
    INSERT INTO documents
        (id, tenant_id, vault_id, case_title, citation, court_level, year,
         source_pdf_path, pdf_sha256)
    VALUES ($1, $2, $3, $4, $5, 'SUPREME_COURT', 2008, 's3://x.pdf', $6)
"""


async def _insert_doc(conn: asyncpg.Connection, tenant: str, citation: str) -> None:
    # RLS USING policy doubles as the WITH CHECK on INSERT (Phase1 §2.1 as
    # written): inserts must carry the tenant GUC inside the transaction.
    async with conn.transaction():
        await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
        await conn.execute(
            INSERT_DOC, uuid.uuid4(), tenant, VAULT_JURIS_NG, f"Case {citation}",
            citation, "aa" * 32,
        )


@pytest.fixture
async def two_tenant_db(app_db_url: str):
    """Fresh documents for the seed tenant plus a second tenant."""
    conn = await asyncpg.connect(app_db_url)
    other = str(uuid.uuid4())
    await conn.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, 'Other LLP', $2)",
        other, f"other-{other[:8]}",
    )
    marker = uuid.uuid4().hex[:8]
    await _insert_doc(conn, SEED_TENANT_AETOES, f"(2008) 5 NWLR-{marker} 227")
    await _insert_doc(conn, other, f"(2011) 3 NWLR-{marker} 1")
    yield conn, SEED_TENANT_AETOES, other
    await conn.close()


class TestTenantIsolation:
    async def test_tenant_sees_only_own_documents(
        self, two_tenant_db: tuple[asyncpg.Connection, str, str]
    ) -> None:
        conn, aetoes, other = two_tenant_db
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", other)
            rows = await conn.fetch("SELECT citation FROM documents")
        assert len(rows) == 1
        assert "(2011)" in rows[0]["citation"]

        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", aetoes)
            rows = await conn.fetch("SELECT citation FROM documents")
        assert len(rows) == 1
        assert "(2008)" in rows[0]["citation"]

    async def test_chunks_isolated_along_with_documents(
        self, two_tenant_db: tuple[asyncpg.Connection, str, str]
    ) -> None:
        conn, aetoes, other = two_tenant_db
        doc_id = uuid.uuid4()
        chunk_id = uuid.uuid4()
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", aetoes)
            await conn.execute(
                INSERT_DOC, doc_id, aetoes, VAULT_JURIS_NG, "Case X", "(1999) 1 NWLR 1",
                "bb" * 32,
            )
            await conn.execute(
                "INSERT INTO document_chunks (id, tenant_id, document_id, chunk_index,"
                " chunk_text, page_start, page_end) VALUES ($1,$2,$3,0,'text',1,1)",
                chunk_id, aetoes, doc_id,
            )
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", other)
            assert await conn.fetchval("SELECT count(*) FROM document_chunks") == 0
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", aetoes)
            assert await conn.fetchval("SELECT count(*) FROM document_chunks") == 1

    async def test_missing_tenant_guc_fails_closed(
        self, two_tenant_db: tuple[asyncpg.Connection, str, str]
    ) -> None:
        # No GUC set in this session: the placeholder default '' cannot cast
        # to UUID, so the query errors and the connection sees NOTHING rather
        # than defaulting to all rows.
        conn, _aetoes, _other = two_tenant_db
        with pytest.raises((asyncpg.DataError, asyncpg.UndefinedObjectError)):
            await conn.fetch("SELECT * FROM documents")

    async def test_cross_tenant_update_invisible(
        self, two_tenant_db: tuple[asyncpg.Connection, str, str]
    ) -> None:
        conn, aetoes, other = two_tenant_db
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.tenant_id', $1, true)", other)
            # RLS USING policy makes tenant A's rows invisible: UPDATE touches 0.
            result = await conn.execute(
                "UPDATE documents SET case_title = 'HIJACKED' "
                "WHERE tenant_id = $1::uuid",
                aetoes,
            )
        assert result == "UPDATE 0"


class TestSeed:
    async def test_aetoes_tenant_seeded(self, app_db_url: str) -> None:
        conn = await asyncpg.connect(app_db_url)
        try:
            row = await conn.fetchrow(
                "SELECT name, jurisdiction FROM tenants WHERE slug = 'aetoes'"
            )
            assert row == ("Aetoes Legal", "NG")
            vault = await conn.fetchrow(
                "SELECT vault_type, is_shared FROM vaults WHERE tenant_id = $1",
                SEED_TENANT_AETOES,
            )
            assert vault == ("juris", True)
        finally:
            await conn.close()
