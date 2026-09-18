"""Debug: raw answer-LLM responses for specific battery questions."""

import asyncio
import json
from pathlib import Path

import asyncpg

from app.config import get_settings
from app.retrieval import service
from app.retrieval.clients import make_embedder, make_llm

QIDS = ["B08", "B12", "B13", "B14"]
TENANT = "a0000001-0000-4000-8000-000000000001"
BATTERY = json.loads(
    Path("tests/fixtures/citation_battery.json").read_text(encoding="utf-8")
)


async def main() -> None:
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("SELECT set_config('app.tenant_id', $1, false)", TENANT)
    embedder = make_embedder(settings)
    llm = make_llm(settings)
    svc = service.RetrievalService(conn, TENANT)
    for qid in QIDS:
        item = next(i for i in BATTERY if i["id"] == qid)
        qvec = (await embedder.embed([item["question"]]))[0]
        rows = await svc.retrieve(
            item["question"], qvec, item.get("filters") or {}, threshold=-1.0
        )
        msg = await llm.answer(
            service.GROUNDED_SYSTEM,
            service.GROUNDED_USER.format(
                question=item["question"],
                filters=item.get("filters") or {},
                passages=svc.build_passages(rows),
            ),
        )
        print(f"===== {qid} :: {item['question'][:70]}")
        print(msg[:1200])
        print()
    await conn.close()


asyncio.run(main())
