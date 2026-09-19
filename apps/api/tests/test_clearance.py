"""Clearance RLS battery — Task 2.1 DoD (Phase2-Design 1.2).

Three synthetic users at different clearances assert ZERO leakage of
CONFIDENTIAL / PARTNER_RESTRICTED material AT THE SQL LEVEL — the
assertion is that a bare SELECT returns no rows, not that an answer
was withheld. Contract under test:

  * vault_a_clearance (documents) + chunk_privilege (document_chunks,
    via vault_type_guard) are the privilege layer; Phase 1 tenant
    isolation stays underneath;
  * visibility: non-firm docs always; FIRM_INTERNAL firm docs always;
    anything above that only for PARTNER/ADMIN or an explicit
    document_grants row for current_setting('app.user_ref');
  * the clearance GUCs use the missing-ok form — unset clearance denies
    firm docs above FIRM_INTERNAL (fail-closed by denial, no error);
  * ALL fixture data is synthetic (owner rule: no real Aetoes documents
    in Vault A until the 2.2 pen-test DoD passes).

Per the verbatim Phase 2 policy, SENIOR sees FIRM_INTERNAL + grants
only — the doc's prose implies SENIOR >= CONFIDENTIAL but the SQL does
not encode it; that gap is flagged to the owner, and this battery locks
the VERBATIN behaviour so any future change is a conscious diff.
"""

import uuid

import asyncpg
import pytest
from conftest import SEED_TENANT_AETOES

VAULT_JURIS_NG = "b0000001-0000-4000-8000-000000000001"

STAFF = ("u-staff-syn", "STAFF")
SENIOR = ("u-senior-syn", "SENIOR")
PARTNER = ("u-partner-syn", "PARTNER")

INSERT_DOC = """
    INSERT INTO documents
        (id, tenant_id, vault_id, case_title, citation, court_level, year,
         source_pdf_path, pdf_sha256, client_id, matter_id,
         classification_level, doc_type)
    VALUES ($1, $2, $3, $4, $5, 'SUPREME_COURT', 2024, 's3://syn.pdf', $6,
            $7, $8, $9, 'BRIEF')
"""

INSERT_CHUNK = """
    INSERT INTO document_chunks
        (id, tenant_id, document_id, chunk_index, chunk_text, page_start, page_end)
    VALUES ($1, $2, $3, 0, $4, 1, 1)
"""


async def _scope(
    conn: asyncpg.Connection,
    tenant: str,
    user_ref: str | None,
    clearance: str | None,
) -> None:
    """Set the request-scoped GUCs inside a transaction (HANDOFF 2.2)."""
    await conn.execute("SELECT set_config('app.tenant_id', $1, true)", tenant)
    if user_ref is not None:
        await conn.execute("SELECT set_config('app.user_ref', $1, true)", user_ref)
    if clearance is not None:
        await conn.execute(
            "SELECT set_config('app.user_clearance', $1, true)", clearance
        )


@pytest.fixture
async def vault_a_fixture(app_db_url: str):
    """One synthetic client + matter + three firm docs (FI/CONF/PR) with
    chunks, plus a Vault B doc/chunk as the unaffected control."""
    conn = await asyncpg.connect(app_db_url)
    marker = uuid.uuid4().hex[:8]
    tenant = SEED_TENANT_AETOES
    firm_vault = uuid.uuid4()
    client_id = uuid.uuid4()
    matter_id = uuid.uuid4()
    docs = {level: uuid.uuid4() for level in ("FIRM_INTERNAL", "CONFIDENTIAL",
                                              "PARTNER_RESTRICTED")}
    juris_doc = uuid.uuid4()
    juris_chunk = uuid.uuid4()
    chunk_ids = {level: uuid.uuid4() for level in docs}

    # Schema setup: no RLS on vaults; clients/matters need the tenant GUC.
    await conn.execute(
        "INSERT INTO vaults (id, tenant_id, vault_type, name, is_shared)"
        " VALUES ($1, $2, 'firm', $3, FALSE)",
        firm_vault, tenant, f"Synthetic Firm Vault {marker}",
    )
    async with conn.transaction():
        # The fixture ingests as the partner — restrictive clearance
        # policies apply to INSERT too, and only PARTNER can register
        # above-FIRM_INTERNAL documents (production ingestion runs as the
        # service role; the test role exercises real policy enforcement).
        await _scope(conn, tenant, PARTNER[0], PARTNER[1])
        await conn.execute(
            "INSERT INTO clients (id, tenant_id, name) VALUES ($1, $2, $3)",
            client_id, tenant, f"Synthetic Client {marker}",
        )
        await conn.execute(
            "INSERT INTO matters (id, tenant_id, client_id, matter_ref)"
            " VALUES ($1, $2, $3, $4)",
            matter_id, tenant, client_id, f"SYN-{marker} v. Syn",
        )
        for level, doc_id in docs.items():
            await conn.execute(
                INSERT_DOC, doc_id, tenant, firm_vault, f"Synthetic {level}",
                f"(2024) 1 SYN-{level[:4]}-{marker}", "cc" * 32, client_id,
                matter_id, level,
            )
            await conn.execute(
                INSERT_CHUNK, chunk_ids[level], tenant, doc_id,
                f"synthetic chunk text {level}",
            )
        # Vault B control: existing juris vault, classification untouched.
        await conn.execute(
            INSERT_DOC, juris_doc, tenant, VAULT_JURIS_NG,
            "Synthetic Juris Control", f"(2024) 2 SYN-{marker}", "dd" * 32,
            None, None, "FIRM_INTERNAL",
        )
        await conn.execute(
            INSERT_CHUNK, juris_chunk, tenant, juris_doc, "juris control chunk"
        )
    yield {
        "conn": conn, "tenant": tenant, "matter_id": matter_id, "docs": docs,
        "chunk_ids": chunk_ids, "juris_doc": juris_doc,
        "juris_chunk": juris_chunk, "marker": marker,
    }
    await conn.close()


async def _visible_doc_levels(fx: dict, user: tuple[str, str] | None) -> set[str]:
    conn: asyncpg.Connection = fx["conn"]
    async with conn.transaction():
        if user is None:
            await _scope(conn, fx["tenant"], None, None)
        else:
            await _scope(conn, fx["tenant"], user[0], user[1])
        rows = await conn.fetch(
            "SELECT id, classification_level FROM documents WHERE matter_id = $1",
            fx["matter_id"],
        )
    return {r["classification_level"] for r in rows}


class TestClearanceBattery:
    async def test_staff_sees_firm_internal_only(self, vault_a_fixture: dict) -> None:
        levels = await _visible_doc_levels(vault_a_fixture, STAFF)
        assert levels == {"FIRM_INTERNAL"}
        assert "PARTNER_RESTRICTED" not in levels
        assert "CONFIDENTIAL" not in levels

    async def test_senior_per_verbatim_policy(self, vault_a_fixture: dict) -> None:
        # Phase 2 1.2's SQL grants SENIOR nothing beyond FIRM_INTERNAL +
        # grants — the prose ordering (PARTNER > SENIOR > STAFF) is NOT in
        # the policy. Locked verbatim; flagged to owner.
        levels = await _visible_doc_levels(vault_a_fixture, SENIOR)
        assert levels == {"FIRM_INTERNAL"}

    async def test_partner_sees_all_classifications(
        self, vault_a_fixture: dict
    ) -> None:
        levels = await _visible_doc_levels(vault_a_fixture, PARTNER)
        assert levels == {"FIRM_INTERNAL", "CONFIDENTIAL", "PARTNER_RESTRICTED"}

    async def test_grant_opens_exactly_that_document(
        self, vault_a_fixture: dict
    ) -> None:
        conn: asyncpg.Connection = vault_a_fixture["conn"]
        tenant = vault_a_fixture["tenant"]
        pr_doc = vault_a_fixture["docs"]["PARTNER_RESTRICTED"]
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)", tenant
            )
            await conn.execute(
                "INSERT INTO document_grants"
                " (tenant_id, document_id, user_ref, grant_level, granted_by)"
                " VALUES ($1, $2, $3, 'READ', $4)",
                tenant, pr_doc, STAFF[0], "u-partner-syn",
            )
        # Granted user: PR visible now, CONFIDENTIAL still not.
        assert await _visible_doc_levels(vault_a_fixture, STAFF) == {
            "FIRM_INTERNAL", "PARTNER_RESTRICTED",
        }
        # A different staff user with no grant: still zero leakage.
        other_staff = (f"u-staff-2-{vault_a_fixture['marker']}", "STAFF")
        assert await _visible_doc_levels(vault_a_fixture, other_staff) == {
            "FIRM_INTERNAL",
        }

    async def test_chunks_mirror_document_clearance(
        self, vault_a_fixture: dict
    ) -> None:
        # Zero PARTNER_RESTRICTED / CONFIDENTIAL chunks reachable by SQL,
        # not merely "no answer produced".
        conn: asyncpg.Connection = vault_a_fixture["conn"]
        conf_chunks = vault_a_fixture["chunk_ids"]["CONFIDENTIAL"]
        pr_chunks = vault_a_fixture["chunk_ids"]["PARTNER_RESTRICTED"]
        fi_chunks = vault_a_fixture["chunk_ids"]["FIRM_INTERNAL"]
        juris_chunks = vault_a_fixture["juris_chunk"]
        async with conn.transaction():
            await _scope(conn, vault_a_fixture["tenant"], STAFF[0], STAFF[1])
            assert await conn.fetchval(
                "SELECT count(*) FROM document_chunks WHERE id = ANY($1::uuid[])",
                [conf_chunks, pr_chunks],
            ) == 0
            assert await conn.fetchval(
                "SELECT count(*) FROM document_chunks WHERE id = $1", fi_chunks
            ) == 1
            # Vault B is classification-blind: unaffected by the new layer.
            assert await conn.fetchval(
                "SELECT count(*) FROM document_chunks WHERE id = $1", juris_chunks
            ) == 1

    async def test_unset_clearance_denies_above_firm_internal(
        self, vault_a_fixture: dict
    ) -> None:
        # Missing-ok GUC contract: no error, but firm docs above
        # FIRM_INTERNAL are denied. (Contrast Phase 1's tenant GUC, which
        # fails closed by error.)
        levels = await _visible_doc_levels(vault_a_fixture, None)
        assert levels == {"FIRM_INTERNAL"}

    async def test_partner_of_other_tenant_sees_nothing(
        self, vault_a_fixture: dict
    ) -> None:
        conn: asyncpg.Connection = vault_a_fixture["conn"]
        other = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO tenants (id, name, slug) VALUES ($1, 'Other LLP', $2)",
            other, f"other-{uuid.uuid4().hex[:8]}",
        )
        async with conn.transaction():
            await _scope(conn, other, PARTNER[0], PARTNER[1])
            rows = await conn.fetch(
                "SELECT count(*) AS n FROM documents WHERE matter_id = $1",
                vault_a_fixture["matter_id"],
            )
        assert rows[0]["n"] == 0

    async def test_cross_tenant_invisible_on_new_tables(
        self, vault_a_fixture: dict
    ) -> None:
        conn: asyncpg.Connection = vault_a_fixture["conn"]
        other = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO tenants (id, name, slug) VALUES ($1, 'Other LLP', $2)",
            other, f"other-{uuid.uuid4().hex[:8]}",
        )
        async with conn.transaction():
            await _scope(conn, other, PARTNER[0], PARTNER[1])
            clients = await conn.fetchval("SELECT count(*) FROM clients")
            matters = await conn.fetchval("SELECT count(*) FROM matters")
            grants = await conn.fetchval("SELECT count(*) FROM document_grants")
        # The shared session DB holds other tests' rows; the assertion is
        # that a foreign-tenant partner sees none of THIS fixture's rows.
        assert clients == 0 and matters == 0 and grants == 0
