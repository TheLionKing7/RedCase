from scripts.analyze_luna_results import analyze


def test_headline_separates_genuine_and_timeout_converted_refusals(capsys) -> None:
    analyze(
        {
            "provider": "explabs",
            "model": "gpt-6-luna",
            "outcomes": [
                {
                    "id": "B01",
                    "pass": True,
                    "reason": "answered",
                    "refusal": False,
                    "final_outcome_category": "answer",
                    "recovered": True,
                },
                {
                    "id": "B02",
                    "pass": False,
                    "reason": "over-refusal",
                    "refusal": True,
                    "final_outcome_category": "genuine_refusal",
                },
                {
                    "id": "B03",
                    "pass": False,
                    "reason": "answer_timeout",
                    "refusal": True,
                    "final_outcome_category": "timeout_converted_refusal",
                },
            ],
        }
    )

    output = capsys.readouterr().out
    assert "3 | 1 | 1 | 1 | 0 | 0" in output
    assert "COMPARISON SCORE (timeout-converted refusals excluded): 1/2" in output
    assert "GENUINE REFUSALS: B02" in output
    assert "TIMEOUT-CONVERTED REFUSALS: B03" in output


def test_legacy_over_refusal_is_disclosed_as_ambiguous(capsys) -> None:
    analyze(
        {
            "outcomes": [
                {"id": "B02", "pass": False, "reason": "over-refusal", "refusal": True}
            ]
        }
    )

    output = capsys.readouterr().out
    assert "1 | 0 | 0 | 0 | 1 | 0" in output
    assert "LEGACY AMBIGUOUS REFUSALS: B02" in output
    assert "not proven genuine" in output