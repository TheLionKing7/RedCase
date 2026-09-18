"""Retrieval-only recall probe (owner brief 2026-09-18): for each failing
battery ID, embed the question ONCE and dump the full candidate set so the
gold chunk can be labeled offline. Zero chat-LLM spend.

Outputs calibration_results/recall_probe_<ts>.json with, per ID:
  question, expect, the top-8 budgeted passage ids (current matrix cell
  8/3/ratio-exempt), and all top-20 candidate rows (id, document, vsim,
  is_ratio, chunk text). Gold labeling happens offline against the dump;
  classification (corpus / ranking / answer-LLM limited) is computed by
  scripts/classify_recall.py once gold ids are added.
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

from app.config import get_settings
from app.retrieval.clients import make_embedder
from app.retrieval.service import RetrievalService

TENANT = "a0000001-0000-4000-8000-000000000001"
BATTERY_PATH = Path("tests/fixtures/citation_battery.json")
REPORT_DIR = Path("calibration_results")

FAILING_18 = [
    "B08", "B12", "B13", "B14", "B20", "B22", "B23", "B25", "B26", "B27",
    "B29", "B31", "B37", "B39", "B45", "B49",
]


async def main() -> None:
    battery = json.loads(BATTERY_PATH.read_text(encoding="utf-8"))  # noqa: ASYNC240
    items = [i for i in battery if i["id"] in FAILING_18]
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        embedder = make_embedder(settings)
        svc = RetrievalService(conn, TENANT)
        out = []
        for item in items:
            qvec = (await embedder.embed([item["question"]]))[0]
            rows = await svc.candidates(
                item["question"], qvec, item.get("filters") or {},
                threshold=-1.0,
            )
            rows = rows or []
            top8 = await svc.retrieve(
                item["question"], qvec, item.get("filters") or {},
                threshold=-1.0, top_k=8, per_doc_cap=3, ratio_exempt=True,
            )
            out.append({
                "id": item["id"],
                "expect": item["expect"],
                "question": item["question"],
                "filters": item.get("filters") or {},
                "top8_ids": [str(r["id"]) for r in (top8 or [])],
                "candidates": [
                    {
                        "id": str(r["id"]),
                        "case_title": r["case_title"],
                        "vsim": r["vsim"],
                        "is_ratio": r["is_ratio"],
                        "chunk_text": r["chunk_text"],
                    }
                    for r in rows
                ],
            })
            print(f"{item['id']}: {len(rows)} candidates", flush=True)
    finally:
        await conn.close()

    REPORT_DIR.mkdir(exist_ok=True)  # noqa: ASYNC240
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = REPORT_DIR / f"recall_probe_{stamp}.json"
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")  # noqa: ASYNC240
    print(f"dump: {path}")


if __name__ == "__main__":
    asyncio.run(main())
