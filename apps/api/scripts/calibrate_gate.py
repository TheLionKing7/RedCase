"""VECTOR_GATE calibration against the citation battery — Task 1.3 DoD.

Measures, for every battery question, the EXACT number the runtime refusal
gate compares: RetrievalService.retrieve() orders candidate chunks by the
hybrid score (0.65*vsim + 0.35*fsim, x1.3 for ratio passages) and gates on
the vsim of the top-SCORE row — which is not necessarily the top-1 vsim
row. Calibrating against plain top-1 vsim therefore mispredicts the
runtime verdict (found 2026-09-18: B01 calibrated 0.689 but refused at
runtime; B09 calibrated 0.674 but answered). This script runs the real
retrieve() with the gate disabled (threshold=-1) and records
rows[0]["vsim"], per question, split by expected class (answer vs
refusal). The calibrated gate is the value that best separates the two
distributions: every candidate midpoint between observed scores is
evaluated by how many battery items it classifies correctly
(answer-questions pass, refusal-questions fail).

Usage:
  python -m scripts.calibrate_gate                      # measure + suggest
  python -m scripts.calibrate_gate --gate 0.42          # also verdict-count

The suggested gate is then set as Settings.vector_gate (config default or
VECTOR_GATE env) and the battery is run for real:
  pytest tests/test_citation_battery.py -v
"""

import argparse
import asyncio
import json
from pathlib import Path

import asyncpg
from openai import RateLimitError

from app.config import get_settings
from app.retrieval.clients import make_embedder
from app.retrieval.service import RetrievalService

BATTERY_PATH = Path("tests/fixtures/citation_battery.json")
SCORES_PATH = Path("calibration_scores.json")
SEED_TENANT = "a0000001-0000-4000-8000-000000000001"


async def _embed_with_backoff(embedder, text: str) -> list[float]:
    """Premium Jina path is uncapped in practice; keep 429 backoff anyway
    so a misconfigured free-tier fallback can't hard-fail a run."""
    for attempt in range(6):
        try:
            return (await embedder.embed([text]))[0]
        except RateLimitError:
            if attempt == 5:
                raise
            wait = 20.0 * (attempt + 1)
            print(f"  rate-limited, waiting {wait:.0f}s ...", flush=True)
            await asyncio.sleep(wait)
    raise AssertionError("unreachable")


def _summarize(scores: list[dict], gate: float | None) -> None:
    answers = sorted(s["gate_vsim"] for s in scores if s["expect"] == "answer")
    refusals = sorted(s["gate_vsim"] for s in scores if s["expect"] == "refusal")

    # Candidate gates: midpoints between consecutive observed scores.
    observed = sorted({s["gate_vsim"] for s in scores})
    best_gate, best_correct = None, -1
    for lo, hi in zip(observed, observed[1:], strict=False):
        cand = (lo + hi) / 2
        correct = sum(
            (s["gate_vsim"] >= cand) if s["expect"] == "answer" else (s["gate_vsim"] < cand)
            for s in scores
        )
        if correct > best_correct:
            best_gate, best_correct = cand, correct

    print(f"\nanswer gate_vsim:  min={answers[0]:.3f} max={answers[-1]:.3f} n={len(answers)}")
    print(f"refusal gate_vsim: min={refusals[0]:.3f} max={refusals[-1]:.3f} n={len(refusals)}")
    if best_gate is not None:
        print(
            f"suggested gate: {best_gate:.3f} "
            f"(classifies {best_correct}/{len(scores)} battery items correctly)"
        )
        overlap = sum(
            1 for s in scores if s["expect"] == "refusal" and s["gate_vsim"] >= best_gate
        )
        if overlap:
            print(
                f"WARNING: {overlap} refusal question(s) score AT/ABOVE the gate"
                " — semantic overlap; consider question or hybrid-weight tuning."
            )
    if gate is not None:
        wrong = [
            s
            for s in scores
            if (s["expect"] == "answer" and s["gate_vsim"] < gate)
            or (s["expect"] == "refusal" and s["gate_vsim"] >= gate)
        ]
        print(f"\nat gate {gate}: {len(scores) - len(wrong)}/{len(scores)} correct")
        for s in wrong:
            print(f"  misclassified {s['id']} ({s['expect']}, gate_vsim={s['gate_vsim']:.3f})")


async def run(
    args: argparse.Namespace, battery: list[dict], prior: dict[str, dict]
) -> dict[str, dict]:
    settings = get_settings()
    settings.require_secrets("database_url")
    embedder = make_embedder(settings)

    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(
            "SELECT set_config('app.tenant_id', $1, false)", SEED_TENANT
        )
        scores: dict[str, dict] = dict(prior)
        svc = RetrievalService(conn, SEED_TENANT)
        for item in battery[args.start - 1 : args.end]:
            if item["id"] in scores and not args.force:
                cached = scores[item["id"]]["gate_vsim"]
                print(
                    f"{item['id']} {item['expect']:7} gate_vsim={cached:.3f} (cached)",
                    flush=True,
                )
                continue
            qvec = await _embed_with_backoff(embedder, item["question"])
            # threshold=-1 disables the gate; candidates()[0] is the top-
            # hybrid-score row, whose vsim is exactly what the runtime gate
            # compares (retrieve() re-orders only the presentation slice).
            rows = await svc.candidates(
                item["question"], qvec, item.get("filters") or {}, threshold=-1.0
            )
            vsim = rows[0]["vsim"] if rows else 0.0
            rec = {
                "id": item["id"],
                "expect": item["expect"],
                "gate_vsim": float(vsim or 0.0),
            }
            scores[item["id"]] = rec
            print(f"{item['id']} {item['expect']:7} gate_vsim={rec['gate_vsim']:.3f}", flush=True)
            await asyncio.sleep(1.0)  # polite pacing; premium tier has headroom
    finally:
        await conn.close()

    if len(scores) == len(battery):
        _summarize(list(scores.values()), args.gate)
    else:
        print(f"\n{len(scores)}/{len(battery)} scored — rerun remaining slices.")
    return scores


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gate", type=float, default=None)
    ap.add_argument("--start", type=int, default=1, help="1-based first battery index")
    ap.add_argument("--end", type=int, default=50, help="1-based exclusive-last battery index")
    ap.add_argument("--force", action="store_true", help="re-embed even if cached")
    ap.add_argument("--summarize-only", action="store_true")
    args = ap.parse_args()
    battery = json.loads(BATTERY_PATH.read_text(encoding="utf-8"))
    if args.summarize_only:
        scores = json.loads(SCORES_PATH.read_text(encoding="utf-8"))
        _summarize(scores, args.gate)
        return
    prior: dict[str, dict] = {}
    if SCORES_PATH.exists():
        prior = {s["id"]: s for s in json.loads(SCORES_PATH.read_text(encoding="utf-8"))}
    scores = asyncio.run(run(args, battery, prior))
    SCORES_PATH.write_text(
        json.dumps(sorted(scores.values(), key=lambda s: s["id"]), indent=1),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
