"""Path-split latency report from query_audit (Task 1.7 step 3 re-measure).

Reconstructs per-question user-experience latency from the audit trail:
query_audit is append-only with one row PER ATTEMPT (v2.1 + one-retry
policy), so a question's total latency is the SUM of its attempts' rows
in created_at order — two refusal rows = one refusal-with-retry event.

Splits:
  answer path            — question whose final row carries answer_text
  refusal-with-retry     — question whose rows are all refusals
  (threshold-only rows, threshold_passed=false with a single refusal
   row and no answer attempt, are reported separately — they never
   reach the answer LLM and owe ~retrieval time only)

Prints p50/p95/max per path against the amended bars (answer <8s,
refusal <15s, ceiling 20s per attempt). Read-only against the audit
table; ZDR-safe (counts and milliseconds only).

Usage:
  python -m scripts.latency_paths --since "2026-09-19 11:50"
"""

import argparse
import asyncio
from datetime import UTC, datetime

import asyncpg

from app.config import get_settings
from scripts.gating_matrix import TENANT


def pct(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * p / 100
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def report(name: str, values: list[float]) -> None:
    if not values:
        print(f"{name}: (no rows)")
        return
    print(
        f"{name}: n={len(values)} p50={pct(values,50)/1000:.1f}s "
        f"p95={pct(values,95)/1000:.1f}s max={max(values)/1000:.1f}s"
    )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--since",
        required=True,
        help='ISO timestamp, e.g. "2026-09-19 11:50" (interpreted as UTC)',
    )
    args = ap.parse_args()
    since = datetime.fromisoformat(args.since).replace(tzinfo=UTC)

    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(
            "SELECT set_config('app.tenant_id', $1, false)", TENANT
        )
        rows = await conn.fetch(
            "SELECT question_hash, latency_ms, answer_text IS NOT NULL AS answered,"
            "       threshold_passed, created_at"
            " FROM query_audit WHERE created_at >= $1 ORDER BY created_at",
            since,
        )
    finally:
        await conn.close()

    # Group attempts per question, in order.
    questions: dict[str, list] = {}
    for r in rows:
        questions.setdefault(r["question_hash"], []).append(r)

    answer_path, refusal_path, threshold_only = [], [], []
    attempts_over_ceiling = 0
    total_attempts = 0
    for attempts in questions.values():
        total = sum(a["latency_ms"] for a in attempts)
        total_attempts += len(attempts)
        attempts_over_ceiling += sum(1 for a in attempts if a["latency_ms"] > 20000)
        final_answered = attempts[-1]["answered"]
        ever_threshold = any(a["threshold_passed"] for a in attempts)
        if final_answered:
            answer_path.append(total)
        elif not ever_threshold and len(attempts) == 1:
            threshold_only.append(total)
        else:
            refusal_path.append(total)

    print(f"window: since {since.isoformat()} | questions={len(questions)} "
          f"attempts={total_attempts}")
    report("answer path          ", answer_path)
    report("refusal-with-retry   ", refusal_path)
    report("threshold-only       ", threshold_only)
    print(f"attempts over 20s ceiling: {attempts_over_ceiling}/{total_attempts}")
    print("\nbars: answer p95 <8s | refusal p95 <15s | per-attempt ceiling 20s")


if __name__ == "__main__":
    asyncio.run(main())
