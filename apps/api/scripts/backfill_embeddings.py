"""Backfill NULL embeddings with the platform embedder — Task 1.3 cleanup.

Chunks ingested under the deferred-embed path (scripts/ingest.py
--no-embed) land with embedding = NULL and refuse retrieval. This script
finds every NULL-embedding chunk (optionally scoped to one tenant/vault),
embeds the chunk text in batches via the configured platform embedder
(app.retrieval.clients.make_embedder — OpenAI ZDR proxy -> OpenRouter ->
NVIDIA NIM precedence), and UPDATEs each row.

Idempotent: already-embedded chunks are skipped, so reruns only cover new
rows. ZDR: no chunk text in logs — ids and counts only.

Usage:
  python -m scripts.backfill_embeddings --tenant aetoes --vault juris
"""

import argparse
import asyncio
import uuid

import asyncpg

from app.config import get_settings
from app.ingestion.db import _vec_literal
from app.middleware.zdr import configure_logging, get_logger
from app.retrieval.clients import make_embedder

log = get_logger("redcase.backfill")


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    settings.require_secrets("database_url")
    embedder = make_embedder(settings)

    conn = await asyncpg.connect(settings.database_url)
    try:
        if args.tenant:
            tenant_id, vault_id = await _resolve_tenant_vault(
                conn, args.tenant, args.vault
            )
            rows = await conn.fetch(
                "SELECT dc.id, dc.chunk_text FROM document_chunks dc"
                " JOIN documents d ON d.id = dc.document_id"
                " WHERE dc.embedding IS NULL AND d.tenant_id = $1"
                " AND ($2::uuid IS NULL OR d.vault_id = $2)"
                " ORDER BY dc.document_id, dc.chunk_index",
                tenant_id,
                vault_id,
            )
        else:
            rows = await conn.fetch(
                "SELECT id, chunk_text FROM document_chunks"
                " WHERE embedding IS NULL ORDER BY document_id, chunk_index"
            )
    finally:
        await conn.close()

    log.info("backfill_start", pending=len(rows), batch_size=args.batch_size)
    done = 0
    for i in range(0, len(rows), args.batch_size):
        batch = rows[i : i + args.batch_size]
        vectors = await embedder.embed([r["chunk_text"] for r in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("embedder returned a mismatched batch size")
        conn = await asyncpg.connect(settings.database_url)
        try:
            async with conn.transaction():
                for row, vec in zip(batch, vectors, strict=True):
                    await conn.execute(
                        "UPDATE document_chunks SET embedding = $2::vector"
                        " WHERE id = $1",
                        row["id"],
                        _vec_literal(vec),
                    )
        finally:
            await conn.close()
        done += len(batch)
        log.info("backfill_progress", done=done, total=len(rows))
    log.info("backfill_done", embedded=done)


async def _resolve_tenant_vault(
    conn: asyncpg.Connection, tenant_slug: str, vault_name: str | None
) -> tuple[uuid.UUID, uuid.UUID | None]:
    if vault_name:
        row = await conn.fetchrow(
            "SELECT v.tenant_id, v.id FROM vaults v"
            " JOIN tenants t ON t.id = v.tenant_id"
            " WHERE t.slug = $1 AND v.name = $2",
            tenant_slug,
            vault_name,
        )
        if row is None:
            raise SystemExit(f"Tenant/vault not found: {tenant_slug}/{vault_name}")
        return row["tenant_id"], row["id"]
    row = await conn.fetchrow(
        "SELECT id FROM tenants WHERE slug = $1", tenant_slug
    )
    if row is None:
        raise SystemExit(f"Tenant not found: {tenant_slug}")
    return row["id"], None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tenant", help="Tenant slug to scope the backfill.")
    ap.add_argument("--vault", help="Vault name to scope the backfill.")
    ap.add_argument("--batch-size", type=int, default=32)
    configure_logging(get_settings().log_level)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
