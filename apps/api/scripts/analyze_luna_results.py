"""Analyze Luna battery outcomes with final-cause refusal attribution."""

import argparse
import json
from pathlib import Path


def _ids(rows: list[dict]) -> str:
    return ", ".join(row["id"] for row in rows) or "none"


def analyze(data: dict) -> None:
    outcomes = data["outcomes"]
    fails = [outcome for outcome in outcomes if not outcome["pass"]]
    timeout_refusals = [
        outcome
        for outcome in outcomes
        if outcome.get("final_outcome_category") == "timeout_converted_refusal"
        or (
            outcome.get("reason_category") == "answer_timeout"
            and outcome.get("refusal") is True
        )
    ]
    timeout_ids = {outcome["id"] for outcome in timeout_refusals}
    explicit_genuine = [
        outcome
        for outcome in outcomes
        if outcome.get("final_outcome_category") == "genuine_refusal"
        or outcome.get("reason_category") == "refusal"
    ]
    explicit_genuine_ids = {outcome["id"] for outcome in explicit_genuine}
    legacy_ambiguous = [
        outcome
        for outcome in outcomes
        if outcome.get("reason") == "over-refusal"
        and outcome["id"] not in timeout_ids
        and outcome["id"] not in explicit_genuine_ids
    ]
    scored = [outcome for outcome in outcomes if outcome["id"] not in timeout_ids]
    scored_passes = sum(outcome["pass"] for outcome in scored)
    other_failures = [
        outcome
        for outcome in fails
        if outcome["id"] not in timeout_ids
        and outcome["id"] not in explicit_genuine_ids
        and outcome["id"] not in {row["id"] for row in legacy_ambiguous}
    ]

    print("HEADLINE SCORE")
    print(
        "Outcomes | Passes | Genuine refusals | Timeout-converted refusals | "
        "Legacy ambiguous refusals | Other failures"
    )
    print(
        f"{len(outcomes)} | {sum(o['pass'] for o in outcomes)} | {len(explicit_genuine)} | "
        f"{len(timeout_refusals)} | {len(legacy_ambiguous)} | {len(other_failures)}"
    )
    print(f"COMPARISON SCORE (timeout-converted refusals excluded): {scored_passes}/{len(scored)}")
    print(f"GENUINE REFUSALS: {_ids(explicit_genuine)}")
    print(f"TIMEOUT-CONVERTED REFUSALS: {_ids(timeout_refusals)}")
    if legacy_ambiguous:
        print(f"LEGACY AMBIGUOUS REFUSALS: {_ids(legacy_ambiguous)}")
        print(
            "NOTE: legacy over-refusals are reported separately because their "
            "final cause is unknown; they are not proven genuine."
        )
    print(f"OTHER FAILURES: {_ids(other_failures)}")
    fabricated = [outcome for outcome in outcomes if "FABRICATED" in outcome.get("reason", "")]
    print(f"FABRICATIONS: {len(fabricated)} ({_ids(fabricated)})")
    print(f"PROVIDER: {data.get('provider', 'unknown')}")
    print(f"MODEL: {data.get('model', 'unknown')}")
    if "pace_s" in data:
        print(f"PACE: {data['pace_s']}s")
    if "run_at" in data:
        print(f"RUN_AT: {data['run_at']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze provider battery outcomes")
    parser.add_argument(
        "--in",
        dest="input_path",
        type=Path,
        default=Path("calibration_results/battery_explabs_luna.json"),
        help="battery JSON (default: calibration_results/battery_explabs_luna.json)",
    )
    args = parser.parse_args()
    analyze(json.loads(args.input_path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
