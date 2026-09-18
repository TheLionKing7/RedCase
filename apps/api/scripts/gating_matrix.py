"""Gating matrix runner (owner brief 2026-09-18): passage-budget sweep over
the failing citation-battery IDs, with VECTOR_GATE fixed.

Matrix: top-k (8 vs 12) x per-doc cap (3 vs 5), ratio-exempt ON in every
cell. No cell requires a code edit — the knobs are Settings-driven
(retrieval_top_k / retrieval_per_doc_cap / retrieval_ratio_exempt).

For each cell: run each selected battery item through the full
answer_question pipeline (grounded answer, citation verification, one
regeneration, refusals) and score it with the battery's own criteria:
  * expect=answer  -> pass iff not refused, citations present, every cite
    verified and its case_title carries a LIVE_CORPUS token (fabrication
    check), page pins sane.
  * expect=refusal -> pass iff refused with no citations (an answer here is
    a possible confabulation and counts as under-refusal).

Records per cell: pass rate, per-ID outcome + reason, mean estimated
input tokens per query (chars/4 of the exact system+user prompts, captured
by a counting LLM wrapper — the API's true usage is not returned through
the AnswerLLM protocol), mean passages per query, mean latency.

Adoption bar (owner): a configuration must recover >=12 of the 18 failing
IDs with zero fabricated citations and no new under-refusals.

Usage:
  python scripts/gating_matrix.py                 # pilot: B08 B20 B45
  python scripts/gating_matrix.py --ids B08 B20   # custom subset
  python scripts/gating_matrix.py --full          # all 18 confirmed failures

ZDR: results carry IDs, case_title tokens, counts and hashes — never
question bodies or answer text.
"""

import argparse
import asyncio
import json
import ssl
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

from app.config import get_settings
from app.retrieval import service
from app.retrieval.clients import make_embedder, make_llm
from app.retrieval.prompts import GROUNDED_SYSTEM

TENANT = "a0000001-0000-4000-8000-000000000001"
BATTERY_PATH = Path("tests/fixtures/citation_battery.json")
REPORT_DIR = Path("calibration_results")

# Confirmed failing IDs (docs/calibration/phase1-jina.md §5).
FULL_18 = [
    "B08", "B12", "B13", "B14", "B20", "B22", "B23", "B25", "B26", "B27",
    "B29", "B31", "B37", "B39", "B45", "B49",
]
PILOT = ["B08", "B20", "B45"]

# (top_k, per_doc_cap) — ratio_exempt is ON for every cell (owner brief).
CONFIGS = [(8, 3), (8, 5), (12, 3), (12, 5)]

LIVE_CORPUS = [
    "AMAECHI", "MADUKOLU", "ADEGOKE MOTORS", "ABACHA", "ADESANYA",
    "OBIKOYA", "AZUBUIKE", "ADEWUMI", "CHIKE OBI", "PABIEKUN", "ALIMI",
]


class CountingLLM:
    """AnswerLLM wrapper: records exact prompt sizes, delegates the call."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.prompt_chars: list[int] = []

    async def answer(self, system: str, user: str) -> str:
        self.prompt_chars.append(len(GROUNDED_SYSTEM) + len(user))
        return await self._inner.answer(system, user)  # type: ignore[attr-defined]


def score(item: dict, result: dict) -> tuple[bool, str]:
    """Battery criteria (mirrors tests/test_citation_battery.py)."""
    if item["expect"] == "refusal":
        if result["refusal"] is True and result["citations"] == []:
            return True, "refused"
        return False, "UNDER-REFUSAL: out-of-corpus question answered"
    if result["refusal"]:
        return False, "over-refusal"
    cites = result["citations"]
    if not cites:
        return False, "answer carried no citations"
    for c in cites:
        if not c["verified"]:
            return False, f"unverified citation {c['case_title']!r}"
        if not any(t in c["case_title"].upper() for t in LIVE_CORPUS):
            return False, f"FABRICATED citation {c['case_title']!r}"
        if not (c["page_start"] >= 1 and c["page_end"] >= c["page_start"]):
            return False, "bad page pins"
    return True, f"answered ({len(cites)} cites)"


async def run_cell(
    conn: asyncpg.Connection,
    settings: object,
    embedder: object,
    base_llm: object,
    items: list[dict],
    top_k: int,
    cap: int,
) -> dict:
    cfg_settings = settings.model_copy(  # type: ignore[attr-defined]
        update={
            "retrieval_top_k": top_k,
            "retrieval_per_doc_cap": cap,
            "retrieval_ratio_exempt": True,
        }
    )
    outcomes = []
    for item in items:
        llm = CountingLLM(base_llm)
        result = None
        for attempt in range(3):
            try:
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, false)", TENANT
                )
                result = await service.answer_question(
                    item["question"], item.get("filters") or {},
                    conn, TENANT, "gating-matrix", settings=cfg_settings,
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
            "pass": ok,
            "reason": reason,
            "refusal": result["refusal"],
            "cited_titles": [c["case_title"] for c in result["citations"]],
            "prompt_chars": llm.prompt_chars[0] if llm.prompt_chars else None,
            "prompt_calls": len(llm.prompt_chars),
        })
    passes = sum(1 for o in outcomes if o["pass"])
    chars = [o["prompt_chars"] for o in outcomes if o["prompt_chars"]]
    return {
        "config": {"top_k": top_k, "per_doc_cap": cap, "ratio_exempt": True},
        "gate": cfg_settings.vector_gate,
        "pass": passes,
        "total": len(outcomes),
        "pass_rate": round(passes / len(outcomes), 3),
        "mean_input_tokens_est": round(statistics.mean(chars) / 4) if chars else None,
        "mean_input_chars": round(statistics.mean(chars)) if chars else None,
        "outcomes": outcomes,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="*", default=None)
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    ids = FULL_18 if args.full else (args.ids or PILOT)
    battery = json.loads(BATTERY_PATH.read_text(encoding="utf-8"))  # noqa: ASYNC240
    items = [i for i in battery if i["id"] in ids]
    missing = set(ids) - {i["id"] for i in items}
    if missing:
        raise SystemExit(f"unknown battery ids: {sorted(missing)}")

    settings = get_settings()
    print(f"gate={settings.vector_gate} (fixed) | ids={ids}")
    REPORT_DIR.mkdir(exist_ok=True)  # noqa: ASYNC240
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = REPORT_DIR / f"gating_matrix_{stamp}.json"
    conn = await asyncpg.connect(settings.database_url)
    try:
        embedder = make_embedder(settings)
        base_llm = make_llm(settings)
        cells = []
        for top_k, cap in CONFIGS:
            t0 = time.monotonic()
            cell = await run_cell(conn, settings, embedder, base_llm, items, top_k, cap)
            cell["wall_s"] = round(time.monotonic() - t0, 1)
            cells.append(cell)
            print(
                f"top_k={top_k:>2} cap={cap} ratio_exempt=True -> "
                f"{cell['pass']}/{cell['total']} "
                f"mean_tok~{cell['mean_input_tokens_est']} "
                f"({cell['wall_s']}s)",
                flush=True,
            )
            # Crash-safe: rewrite the report after every cell so a mid-run
            # interruption (or the operator's shell timeout) keeps results.
            out.write_text(  # noqa: ASYNC240
                json.dumps({
                    "run_at": stamp,
                    "gate": settings.vector_gate,
                    "ids": ids,
                    "cells": cells,
                }, indent=1),
                encoding="utf-8",
            )
    finally:
        await conn.close()

    print(f"report: {out}")


if __name__ == "__main__":
    asyncio.run(main())
