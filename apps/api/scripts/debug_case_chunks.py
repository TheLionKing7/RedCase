"""Debug: list all chunks of a case with per-question vsim."""

import asyncio
import json
from pathlib import Path

import asyncpg

from app.config import get_settings
from app.retrieval.clients import make_embedder

QID = "B11"
CASE = "Madukolu"
TENANT = "a0000001-0000-4000-8000-000000000001"

SQL = """
    SELECT dc.page_start, dc.page_end, dc.is_ratio,
           1 - (dc.embedding <=> $1::vector) AS vsim,
           left(dc.chunk_text, 90) AS preview
    FROM document_chunks dc JOIN documents d ON d.id = dc.document_id
    WHERE d.case_title ILIKE '%' || $2 || '%'
    ORDER BY vsim DESC
"""

BATTERY = json.loads(
    Path("tests/fixtures/citation_battery.json").read_text(encoding="utf-8")
)


async def main() -> None:
    item = next(i for i in BATTERY if i["id"] == QID)
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("SELECT set_config('app.tenant_id', $1, false)", TENANT)
    embedder = make_embedder(settings)
    qvec = (await embedder.embed([item["question"]]))[0]
    lit = "[" + ",".join(repr(float(x)) for x in qvec) + "]"
    rows = await conn.fetch(SQL, lit, CASE)
    print(f"{len(rows)} chunks for {CASE}; question: {item['question'][:80]}")
    for r in rows:
        print(
            f"p{r['page_start']}-{r['page_end']} ratio={r['is_ratio']} "
            f"vsim={round(r['vsim'], 3)}  {r['preview']!r}"
        )
    await conn.close()


asyncio.run(main())
