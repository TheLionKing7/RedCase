"""RedCase Vault B ingestion: PDFs -> metadata -> page-tracked chunks -> pgvector.

Usage:
  python -m scripts.ingest --dir ./fixtures --tenant aetoes --vault juris \
      --concurrency 4 --dry-run

Task 1.3 (Phase1-Design 4). ZDR: no document text in logs — the ZDR structlog
filter from Task 1.1 guards this process (convention 1).
"""

import argparse
import asyncio
import uuid
from pathlib import Path

import asyncpg
from openai import AsyncOpenAI

from app.config import get_settings
from app.ingestion.chunker import chunk_pages, extract_pages
from app.ingestion.db import Embedder, ingest_pdf
from app.ingestion.metadata import extract_metadata
from app.middleware.zdr import configure_logging, get_logger

log = get_logger("redcase.ingest.cli")


class ZdrProxyEmbedder:
    """text-embedding-3-large via the no-retention embedding gateway."""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        r = await self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in r.data]


async def resolve_tenant_vault(
    conn: asyncpg.Connection, tenant_slug: str, vault_name: str
) -> tuple[uuid.UUID, uuid.UUID]:
    row = await conn.fetchrow(
        "SELECT v.tenant_id, v.id FROM vaults v JOIN tenants t ON t.id = v.tenant_id"
        " WHERE t.slug = $1 AND v.name = $2",
        tenant_slug, vault_name,
    )
    if row is None:
        raise SystemExit(f"Tenant/vault not found: {tenant_slug}/{vault_name}")
    return row["tenant_id"], row["id"]


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    pdf_dir = Path(args.dir)
    pdfs = await asyncio.to_thread(lambda: sorted(pdf_dir.glob("**/*.pdf")))
    if not pdfs:
        raise SystemExit(f"No PDFs found under {pdf_dir}")
    log.info("ingest_start", dir=str(pdf_dir), pdfs=len(pdfs), dry_run=args.dry_run)

    if args.dry_run:
        for pdf in pdfs:
            import pymupdf

            with pymupdf.open(pdf) as doc:
                pages = extract_pages(doc)
            meta = extract_metadata("\n".join(pages), pdf.stem)
            chunks = chunk_pages(pages)
            print(
                f"[dry-run] {pdf.name}: {meta.citation} | {meta.court_level} "
                f"{meta.year} | {len(chunks)} chunks | confidence "
                f"{meta.metadata_confidence}"
            )
        return

    settings.require_secrets("database_url", "openai_api_key")
    oai = AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        base_url=settings.zdr_embed_proxy or None,
    )
    embedder: Embedder = ZdrProxyEmbedder(oai, settings.embed_model)
    sem = asyncio.Semaphore(args.concurrency)

    pool = await asyncpg.create_pool(
        settings.database_url, min_size=1, max_size=args.concurrency
    )
    try:
        async with pool.acquire() as conn:
            tenant_id, vault_id = await resolve_tenant_vault(
                conn, args.tenant, args.vault
            )

        async def one(pdf: Path) -> None:
            async with sem, pool.acquire() as conn:
                result = await ingest_pdf(
                    conn, tenant_id=tenant_id, vault_id=vault_id,
                    pdf_path=pdf, embedder=embedder,
                )
                state = "skipped (exists)" if result.skipped else "ingested"
                print(f"[{state}] {pdf.name}: {result.chunks} chunks -> {result.citation}")

        await asyncio.gather(*(one(p) for p in pdfs))
    finally:
        await pool.close()
    log.info("ingest_done", pdfs=len(pdfs))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--tenant", required=True)
    ap.add_argument("--vault", required=True)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    configure_logging(get_settings().log_level)
    asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    main()
