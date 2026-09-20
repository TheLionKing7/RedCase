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
  python -m scripts.run_battery --provider explabs \
      --out calibration_results/battery_explabs.json --pace 25
  ANSWER_MODEL_PRIMARY=cerebras python -m scripts.run_battery \
      --out calibration_results/battery_cerebras.json --pace 15

Provenance: the output header records the INTENDED provider/model; each
outcome records the provider/model that ACTUALLY served it. Provider 429s are
backed off (Retry-After or 15/30/60 s jitter, max 3); a still-limited item is
classified "not_run_rate_limited" and left absent from outcomes for the next
pass — never scored.
"""

import argparse
import asyncio
import json
import random
import ssl
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

from app.config import get_settings
from app.retrieval.clients import RateLimitedError, make_embedder, make_llm
from app.retrieval.service import answer_question
from scripts.gating_matrix import TENANT, score

BATTERY_PATH = Path("tests/fixtures/citation_battery.json")
DEFAULT_OUT = Path("calibration_results/battery_v2.json")

# Model field per provider, for output-header provenance.
_MODEL_FIELD = {
    "explabs": "explabs_model",
    "mistral": "mistral_model",
    "cerebras": "cerebras_model",
    "groq": "groq_model",
    "deepseek": "deepseek_model",
    "openrouter": "llm_model",
}

# Rate-limit backoff for the runner (provider 429): honor Retry-After when
# advertised, else 15/30/60 s base with jitter, max 3 retries. A rate-limited
# item is classified "not_run_rate_limited" and left OUT of outcomes.
_RATE_BACKOFF_SECONDS = (15.0, 30.0, 60.0)
MAX_RATE_RETRIES = 3


def _rate_backoff_delay(retry: int) -> float:
    """Jittered backoff (retry is 0-indexed): 15/30/60 s base +0-50% jitter."""
    base = _RATE_BACKOFF_SECONDS[retry]
    return base + random.uniform(0.0, base * 0.5)  # noqa: S311 — jitter, not crypto


async def _run_item(item, conn, settings, embedder, llm):
    """Answer one battery item with provider-429 backoff.

    Returns (result, rate_limited). Transient TLS drops retry the query (3
    attempts, same connection). Provider 429s back off (Retry-After or
    15/30/60 jitter, max 3); if still limited, returns rate_limited=True so
    the caller leaves the item ABSENT from outcomes — never scored.
    """
    for attempt in range(3):
        try:
            await conn.execute("SELECT set_config('app.tenant_id', $1, false)", TENANT)
            for rl in range(MAX_RATE_RETRIES + 1):
                try:
                    result = await answer_question(
                        item["question"], item.get("filters") or {},
                        conn, TENANT, "battery-v2", settings=settings,
                        embedder=embedder, llm=llm,
                    )
                    return result, False
                except RateLimitedError as exc:
                    if rl == MAX_RATE_RETRIES:
                        return None, True
                    delay = (
                        exc.retry_after
                        if exc.retry_after is not None
                        else _rate_backoff_delay(rl)
                    )
                    print(
                        f"{item['id']}: rate-limited ({exc.provider}/{exc.model}), "
                        f"backoff {delay:.1f}s (retry {rl + 1}/{MAX_RATE_RETRIES})",
                        flush=True,
                    )
                    await asyncio.sleep(delay)
        except ssl.SSLError:
            if attempt == 2:
                raise
    raise RuntimeError(f"{item['id']}: no result after retries")


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
    ap.add_argument(
        "--provider",
        type=str,
        default=None,
        help="measure this provider ALONE (override primary + clear fallback) for the run",
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
    if args.provider:
        # Override ANSWER_MODEL_PRIMARY AND clear the fallback chain for THIS
        # run only — a calibration run must measure the named provider alone,
        # so a transient 429 surfaces as "not_run_rate_limited" (resumable)
        # rather than silently falling through to a weaker provider and
        # blending quality/latency evidence. The cached global Settings (and
        # hence the live serving config) is untouched.
        settings = settings.model_copy(
            update={"answer_model_primary": args.provider, "answer_model_fallback": ""}
        )
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
            result, rate_limited = await _run_item(item, conn, settings, embedder, llm)
            if rate_limited:
                print(
                    f"{item['id']}: not_run_rate_limited — skipped (resume next pass)",
                    flush=True,
                )
                continue  # absent from outcomes -> picked up next pass
            if result is None:
                raise RuntimeError(f"{item['id']}: no result after retries")
            ok, reason = score(item, result)
            # Per-item provenance = what ACTUALLY served (the resolved provider
            # today; the runtime fallback chain updates llm.provider once landed).
            served_provider = getattr(llm, "provider", primary)
            served_model = getattr(llm, "model", model)
            outcomes.append({
                "id": item["id"],
                "expect": item["expect"],
                "pass": ok,
                "reason": reason,
                "refusal": result["refusal"],
                "cited_titles": [c["case_title"] for c in result["citations"]],
                "provider": served_provider,
                "model": served_model,
            })
            print(
                f"{item['id']}: {'PASS' if ok else 'FAIL'} | {reason} | "
                f"{served_provider}/{served_model}",
                flush=True,
            )
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
