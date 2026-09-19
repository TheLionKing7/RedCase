"""Full 50-question citation battery runner with resume and provider pacing.

Runs every battery item through answer_question with production defaults
(gate 0.52, budget 8/3, ratio_exempt off) and the CURRENT GROUNDED_SYSTEM,
scoring with the battery's own criteria (same score() as the gating
matrix). Writes results incrementally to calibration_results/battery_v2.json
— re-running the command skips IDs already present, so shell timeouts
cannot lose progress.

PACING (owner ruling 2026-09-19): free-tier providers throttle on
requests-per-minute, and the un-paced runner trips Groq's ceiling every
run. --pace (default 12 s, the 10–15 s approved band) sleeps BETWEEN
calls — retrieval for item N+1 still starts immediately after the sleep,
so wall-clock cost is pace + answer time per item, not pace stacked on
retrieval.

Provider selection is the standard env-selectable chain: the run records
which primary/fallback chain and model served it in the output header,
so calibration files are self-describing.

Usage:
  python -m scripts.run_battery                          # all 50, resuming
  python -m scripts.run_battery --ids B20 B45            # subset (fresh scores)
  ANSWER_MODEL_PRIMARY=groq python -m scripts.run_battery \
      --out calibration_results/battery_groq.json        # paced Groq run
  ANSWER_MODEL_PRIMARY=cerebras python -m scripts.run_battery \
      --out calibration_results/battery_cerebras.json --pace 15
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
DEFAULT_OUT = Path("calibration_results/battery_v2.json")

# Model field per provider, for output-header provenance.
_MODEL_FIELD = {
    "mistral": "mistral_model",
    "cerebras": "cerebras_model",
    "groq": "groq_model",
    "deepseek": "deepseek_model",
    "openrouter": "llm_model",
}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=None)
    ap.add_argument(
        "--pace",
        type=float,
        default=12.0,
        help="seconds to wait BETWEEN answer calls (default 12; owner band 10-15)",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="results file (default calibration_results/battery_v2.json)",
    )
    args = ap.parse_args()

    battery = json.loads(BATTERY_PATH.read_text(encoding="utf-8"))  # noqa: ASYNC240
    if args.ids:
        items = [i for i in battery if i["id"] in args.ids]
    else:
        done = set()
        if args.out.exists():  # noqa: ASYNC240
            done = {o["id"] for o in json.loads(args.out.read_text(encoding="utf-8"))["outcomes"]}  # noqa: ASYNC240
        items = [i for i in battery if i["id"] not in done]
    print(f"items to run: {[i['id'] for i in items]}", flush=True)

    settings = get_settings()
    primary = settings.answer_model_primary
    model = getattr(settings, _MODEL_FIELD.get(primary, "llm_model"), None)
    conn = await asyncpg.connect(settings.database_url)
    try:
        embedder = make_embedder(settings)
        llm = make_llm(settings)
        outcomes = []
        if args.out.exists():  # noqa: ASYNC240
            outcomes = json.loads(args.out.read_text(encoding="utf-8"))["outcomes"]  # noqa: ASYNC240
        for idx, item in enumerate(items):
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
            args.out.write_text(json.dumps({  # noqa: ASYNC240
                "run_at": datetime.now(UTC).isoformat(),
                "prompt": "GROUNDED_SYSTEM current (v2.1)",
                "provider": primary,
                "model": model,
                "pace_s": args.pace,
                "outcomes": outcomes,
            }, indent=1), encoding="utf-8")
            # Pace BETWEEN calls only — the last item owes no sleep.
            if args.pace > 0 and idx < len(items) - 1:
                await asyncio.sleep(args.pace)
    finally:
        await conn.close()

    total = len(outcomes)
    passes = sum(1 for o in outcomes if o["pass"])
    fab = [o["id"] for o in outcomes if "FABRICATED" in o["reason"]]
    print(f"\nTOTAL {passes}/{total} | fabricated: {fab or 'none'}")


if __name__ == "__main__":
    asyncio.run(main())
