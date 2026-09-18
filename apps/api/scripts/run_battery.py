"""Full 50-question citation battery runner with resume (prompt v2 gate).

Runs every battery item through answer_question with production defaults
(gate 0.52, budget 8/3, ratio_exempt off) and the CURRENT GROUNDED_SYSTEM,
scoring with the battery's own criteria (same score() as the gating
matrix). Writes results incrementally to calibration_results/battery_v2.json
— re-running the command skips IDs already present, so shell timeouts
cannot lose progress.

Usage:
  python -m scripts.run_battery                # all 50, resuming
  python -m scripts.run_battery --ids B20 B45  # subset (fresh scores)
"""

import argparse
import asyncio
import json
import ssl
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

from app.config import get_settings
from app.retrieval.clients import make_embedder, make_llm
from app.retrieval.service import answer_question
from scripts.gating_matrix import TENANT, score

BATTERY_PATH = Path("tests/fixtures/citation_battery.json")
OUT_PATH = Path("calibration_results/battery_v2.json")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=None)
    args = ap.parse_args()

    battery = json.loads(BATTERY_PATH.read_text(encoding="utf-8"))  # noqa: ASYNC240
    if args.ids:
        items = [i for i in battery if i["id"] in args.ids]
    else:
        done = set()
        if OUT_PATH.exists():  # noqa: ASYNC240
            done = {o["id"] for o in json.loads(OUT_PATH.read_text(encoding="utf-8"))["outcomes"]}  # noqa: ASYNC240
        items = [i for i in battery if i["id"] not in done]
    print(f"items to run: {[i['id'] for i in items]}", flush=True)

    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        embedder = make_embedder(settings)
        llm = make_llm(settings)
        outcomes = []
        if OUT_PATH.exists():  # noqa: ASYNC240
            outcomes = json.loads(OUT_PATH.read_text(encoding="utf-8"))["outcomes"]  # noqa: ASYNC240
        for item in items:
            result = None
            for attempt in range(3):
                try:
                    await conn.execute(
                        "SELECT set_config('app.tenant_id', $1, false)", TENANT
                    )
                    result = await answer_question(
                        item["question"], item.get("filters") or {},
                        conn, TENANT, "battery-v2", settings=settings,
                        embedder=embedder, llm=llm,
                    )
                    break
                except ssl.SSLError:
                    if attempt == 2:
                        raise
            if result is None:
                raise RuntimeError(f"{item['id']}: no result after retries")
            ok, reason = score(item, result)
            outcomes.append({
                "id": item["id"],
                "expect": item["expect"],
                "pass": ok,
                "reason": reason,
                "refusal": result["refusal"],
                "cited_titles": [c["case_title"] for c in result["citations"]],
            })
            print(f"{item['id']}: {'PASS' if ok else 'FAIL'} | {reason}", flush=True)
            OUT_PATH.write_text(json.dumps({  # noqa: ASYNC240
                "run_at": datetime.now(UTC).isoformat(),
                "prompt": "GROUNDED_SYSTEM v2",
                "outcomes": outcomes,
            }, indent=1), encoding="utf-8")
    finally:
        await conn.close()

    total = len(outcomes)
    passes = sum(1 for o in outcomes if o["pass"])
    fab = [o["id"] for o in outcomes if "FABRICATED" in o["reason"]]
    print(f"\nTOTAL {passes}/{total} | fabricated: {fab or 'none'}")


if __name__ == "__main__":
    asyncio.run(main())
