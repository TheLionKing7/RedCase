"""Vault A intake pipeline — Task 2.3 (Phase2 3.5 + owner rulings 2026-09-19).

PDF bytes -> chunked, embedded, optionally encrypted Vault A document
under a matter, with hash idempotency and the default ACL. Slack intake
(Task 2.6) is a CLIENT of this module — nothing here touches Slack.

Owner rulings folded in (design-doc conflicts recorded, rule 3):
  * DEFAULT classification for client-related documents is CONFIDENTIAL —
    never FIRM_INTERNAL (ruling 1; Phase2 3.5's LLM classification step
    is demoted to a future curation aid, not the trust boundary).
  * PARTNER_RESTRICTED is opt-in and requires NAMED grantees; class-level
    grants ("all partners") are rejected outright — the 2.2 grant-gated
    ruling must not be re-defeated by the default ACL (ruling 1).
  * Default ACL = uploader + explicitly named individuals only
    (replaces Phase2 3.5's "uploader + partners on the matter").
  * Write authorization is APP-LAYER (ruling 2a): 0009's WITH CHECK(true)
    deliberately left writes to the application; this module is where
    that authority lives. Reads remain SQL-enforced (pen-test stands).

CONFLICT RECORDED (rule 3): Phase2 3.5 passes year=None to documents,
but the Phase 1 schema (migration 0001, design 2.1 verbatim) has
year INT NOT NULL. Intake stamps the current year — the smallest
correction that keeps the schema contract; flagged to the owner.

Intake-provisioned default-ACL grants run under an elevated internal
clearance scope: grant creation for the uploader + named grantees is
part of intake, authorized here per the rulings above. The SQL
grant_admin policy still denies USER-DRIVEN grant inserts below
PARTNER (the 2.2 pen-test is untouched).

ZDR: plaintext exists only in worker memory between extraction and
encryption; nothing is logged (HANDOFF.md 2.1).
"""

import hashlib
import re
import uuid
from datetime import UTC, datetime

import asyncpg
import fitz  # PyMuPDF

from app.config import Settings
from app.ingestion.chunker import chunk_pages, extract_pages
from app.vault_a.crypto import (
    KeyProvider,
    decrypt_chunk_text,
    encrypt_chunk_text,
    generate_dek,
    needs_encryption,
)
from app.vault_a.docx import DocxError, extract_docx_text

DEFAULT_CLASSIFICATION = "CONFIDENTIAL"  # ruling 1 — never FIRM_INTERNAL
CLASSIFICATIONS = ("PUBLIC", "FIRM_INTERNAL", "CONFIDENTIAL", "PARTNER_RESTRICTED")
DOC_TYPES = ("BRIEF", "PLEADING", "OPINION", "CONTRACT", "CORRESPONDENCE", "OTHER")
# Class-level / wildcard grantee spells that must never become grant rows.
# Matched against the whole grantee and against each whitespace-separated
# token, so multi-word class phrases ("all partners", "every partner")
# are caught as well as bare class words. False-positive cost (a surname
# like "Partners" is rejected) is accepted under the ruling-1 strictness.
GRANTEE_DENYLIST = frozenset({
    "all", "partners", "partner", "everyone", "*",
    "staff", "seniors", "admins",
})
_ADMIN_CLEARANCES = ("PARTNER", "ADMIN")


class IntakeError(ValueError):
    """Validation/authorization failure — mapped to 4xx by the route.

    code 403 = authorization ruling violation (PR below PARTNER, grantees
    beyond authority, class-level grantee spell); 422 = malformed input.
    """

    def __init__(self, message: str, code: int = 422) -> None:
        super().__init__(message)
        self.code = code


def _parse_grantees(raw: str | None) -> list[str]:
    """Named individuals only; class-level grantees are a ruling-1 violation."""
    if not raw:
        return []
    grantees = [g.strip() for g in raw.split(",") if g.strip()]
    for g in grantees:
        tokens = g.lower().split()
        if g.lower() in GRANTEE_DENYLIST or any(
            t in GRANTEE_DENYLIST for t in tokens
        ):
            raise IntakeError(
                f"grantee {g!r} is a class-level grant — PARTNER_RESTRICTED "
                "requires named individuals only (owner ruling 2.3)",
                code=403,
            )
    return grantees


def authorize_intake(
    *,
    classification: str,
    grantees: list[str],
    uploader_clearance: str,
) -> None:
    """App-layer write authorization (ruling 2a). Raises IntakeError."""
    if classification == "PARTNER_RESTRICTED":
        if uploader_clearance not in _ADMIN_CLEARANCES:
            raise IntakeError(
                "PARTNER_RESTRICTED intake requires PARTNER or ADMIN clearance",
                code=403,
            )
        if not grantees:
            raise IntakeError(
                "PARTNER_RESTRICTED intake requires at least one named grantee",
                code=422,
            )
    elif grantees and uploader_clearance not in _ADMIN_CLEARANCES:
        raise IntakeError(
            "naming grantees requires PARTNER or ADMIN clearance",
            code=403,
        )


def resolve_classification(raw: str | None) -> str:
    if raw is None or raw == "":
        return DEFAULT_CLASSIFICATION
    level = raw.strip().upper()
    if level not in CLASSIFICATIONS:
        raise IntakeError(f"unknown classification_level {raw!r}")
    return level


async def find_by_hash(
    conn: asyncpg.Connection, tenant_id: str, digest: str
) -> uuid.UUID | None:
    """Hash idempotency guard (3.5): identical bytes -> same document."""
    row = await conn.fetchrow(
        "SELECT d.id FROM documents d JOIN vaults v ON v.id = d.vault_id"
        " WHERE d.tenant_id = $1::uuid AND d.pdf_sha256 = $2"
        " AND v.vault_type = 'firm'",
        tenant_id,
        digest,
    )
    return row["id"] if row else None


async def _provision_default_acl(
    conn: asyncpg.Connection,
    *,
    tenant_id: str,
    document_id: uuid.UUID,
    uploader: str,
    grantees: list[str],
) -> None:
    """Default ACL (ruling 1): uploader + named individuals, nothing else.

    Elevated internal scope: intake-authorized grant provisioning (see
    module docstring). granted_by records the real uploader for audit.
    """
    await conn.execute(
        "SELECT set_config('app.user_clearance', 'PARTNER', true)"
    )
    for user_ref in dict.fromkeys([uploader, *grantees]):
        await conn.execute(
            "INSERT INTO document_grants"
            " (tenant_id, document_id, user_ref, grant_level, granted_by)"
            " VALUES ($1, $2, $3, 'READ', $4)",
            uuid.UUID(tenant_id),
            document_id,
            user_ref,
            uploader,
        )


async def intake_document(
    *,
    conn: asyncpg.Connection,
    settings: Settings,
    provider: KeyProvider,
    embedder,
    tenant_id: str,
    uploader: str,
    uploader_clearance: str,
    matter_id: uuid.UUID,
    raw: bytes,
    filename: str,
    classification: str | None = None,
    doc_type: str | None = None,
    grantees: list[str] | None = None,
) -> dict:
    """Ingest PDF or DOCX bytes into Vault A. Returns document metadata.

    ``conn`` must already carry the request scope (app.tenant_id /
    app.user_ref / app.user_clearance set in the current transaction) —
    RLS on reads and the tenant GUC on writes both come from it.
    """
    level = resolve_classification(classification)
    named = list(grantees or [])
    authorize_intake(
        classification=level, grantees=named, uploader_clearance=uploader_clearance
    )
    dtype = (doc_type or "OTHER").strip().upper()
    if dtype not in DOC_TYPES:
        raise IntakeError(f"unknown doc_type {doc_type!r}")

    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    if extension not in {"pdf", "docx"}:
        raise IntakeError("only PDF and DOCX uploads are supported")

    digest = hashlib.sha256(raw).hexdigest()
    if existing := await find_by_hash(conn, str(tenant_id), digest):
        return {
            "document_id": str(existing),
            "duplicate": True,
            "classification_level": level,
            "chunks": 0,
        }

    # Chunk + embed from plaintext (worker-memory only; ZDR). The dedup key
    # remains the hash of the original upload bytes for both formats.
    if extension == "docx":
        try:
            pages = [extract_docx_text(raw)]
        except DocxError as exc:
            raise IntakeError(str(exc)) from exc
    else:
        try:
            with fitz.open(stream=raw, filetype="pdf") as pdf:
                pages = extract_pages(pdf)
        except Exception as exc:  # noqa: BLE001 — mapped to a 4xx by the route
            raise IntakeError(f"unparseable PDF: {type(exc).__name__}") from exc
    chunks = chunk_pages(pages)
    if not chunks:
        raise IntakeError("PDF contains no extractable text")
    vectors = await embedder.embed([c.text for c in chunks])

    doc_id = uuid.uuid4()
    aad = str(doc_id).encode()
    encrypted = needs_encryption(level)
    dek = generate_dek() if encrypted else None
    stored_texts = [
        encrypt_chunk_text(dek, c.text, aad) if encrypted else c.text
        for c in chunks
    ]
    wrapped = provider.wrap(dek, aad) if encrypted else None
    content_hash = provider.content_hash(raw) if encrypted else None

    matter = await conn.fetchrow(
        "SELECT client_id FROM matters WHERE id = $1", matter_id
    )
    if matter is None:
        raise IntakeError("matter not found in this tenant")

    title = re.sub(r"\.(pdf|docx)$", "", filename, flags=re.I) or f"Document {digest[:8]}"
    await conn.execute(
        "INSERT INTO documents"
        " (id, tenant_id, vault_id, case_title, citation, court_level, year,"
        "  source_pdf_path, pdf_sha256, client_id, matter_id,"
        "  classification_level, doc_type, encrypted_content_hash, dek_wrapped,"
        "  metadata_confidence)"
        " SELECT $1, $2, v.id, $3, $4, 'STATUTE', $5, $6, $7, $8, $9, $10, $11,"
        "        $12, $13, 1.0"
        " FROM vaults v"
        " WHERE v.tenant_id = $2::uuid AND v.vault_type = 'firm' LIMIT 1",
        doc_id,
        str(tenant_id),
        title,
        f"INTERNAL-{digest[:12]}",
        datetime.now(UTC).year,  # year NOT NULL (0001) — design's None corrected
        f"vault-a/{digest[:16]}.pdf",
        digest,
        matter["client_id"],
        matter_id,
        level,
        dtype,
        content_hash,
        wrapped,
    )
    for idx, (chunk, vec, stored) in enumerate(zip(chunks, vectors, stored_texts, strict=True)):
        await conn.execute(
            "INSERT INTO document_chunks"
            " (id, tenant_id, document_id, chunk_index, chunk_text,"
            "  page_start, page_end, paragraph_refs, is_ratio, embedding)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::vector)",
            uuid.uuid4(),
            str(tenant_id),
            doc_id,
            idx,
            stored,
            chunk.page_start,
            chunk.page_end,
            chunk.paragraph_refs,
            chunk.is_ratio,
            "[" + ",".join(repr(float(x)) for x in vec) + "]",
        )
    await _provision_default_acl(
        conn,
        tenant_id=str(tenant_id),
        document_id=doc_id,
        uploader=uploader,
        grantees=named,
    )
    return {
        "document_id": str(doc_id),
        "duplicate": False,
        "classification_level": level,
        "chunks": len(chunks),
    }


async def read_document_decrypted(
    *,
    conn: asyncpg.Connection,
    provider: KeyProvider,
    document_id: uuid.UUID,
) -> dict | None:
    """Decrypt-on-retrieve read path (DoD 2c): metadata + plaintext chunks
    for the CALLER as scoped by RLS. Invisible documents return None (the
    route maps it to 404 — no existence oracle). Stored rows stay
    ciphertext; decryption happens here and in nothing else.
    """
    doc = await conn.fetchrow(
        "SELECT id, case_title, classification_level, dek_wrapped, matter_id"
        " FROM documents WHERE id = $1",
        document_id,
    )
    if doc is None:
        return None
    chunks = await conn.fetch(
        "SELECT chunk_text, page_start, page_end, paragraph_refs"
        " FROM document_chunks WHERE document_id = $1 ORDER BY chunk_index",
        document_id,
    )
    dek = None
    if doc["dek_wrapped"] is not None:
        dek = provider.unwrap(doc["dek_wrapped"], str(document_id).encode())
    aad = str(document_id).encode()
    return {
        "document_id": str(document_id),
        "case_title": doc["case_title"],
        "classification_level": doc["classification_level"],
        "chunks": [
            {
                "text": (
                    decrypt_chunk_text(dek, c["chunk_text"], aad)
                    if dek is not None
                    else c["chunk_text"]
                ),
                "page_start": c["page_start"],
                "page_end": c["page_end"],
                "paragraph_refs": [str(p) for p in (c["paragraph_refs"] or [])],
            }
            for c in chunks
        ],
    }
