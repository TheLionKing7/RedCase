"""Count ingested documents for the seed tenant (retry-loop helper)."""

import asyncio
import os

import asyncpg

TENANT = "a0000001-0000-4000-8000-000000000001"


async def main() -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    print(await conn.fetchval("SELECT count(*) FROM documents WHERE tenant_id = $1", TENANT))
    await conn.close()


asyncio.run(main())
