"""50-question citation battery — Task 1.5 corpus-dependent DoD.

DoD contract (HANDOFF.md 4 / Phase1-Design 3.4): run the battery against the
10 benchmark Supreme Court PDFs in ./fixtures; ZERO fabricated citations
allowed — every returned citation must be page-pinned to a retrieved chunk,
and out-of-corpus questions must produce refusals, not confabulation.

STATUS: RUNNABLE (owner 2026-09-18). Embeddings are backfilled at 2048
dims (nemotron via OpenRouter, migration 0006) and the answer LLM
resolves from DeepSeek (DEEPSEEK_API_KEY) or OpenRouter chat
(settings.llm_model). Settings load from the real .env via
get_settings() — this module is the one test suite that REQUIRES live
credentials, so keep every other test on Settings(_env_file=None).

Run:  pytest tests/test_citation_battery.py -v
(after VECTOR_GATE calibration — see scripts/ingest.py for the corpus)
"""

import json
from pathlib import Path

import asyncpg
import pytest

from app.config import get_settings
from app.retrieval.service import answer_question

BATTERY_PATH = Path(__file__).parent / "fixtures" / "citation_battery.json"
SEED_TENANT = "a0000001-0000-4000-8000-000000000001"

# Party tokens of the judgments live in the vault (verified 2026-09-18
# against extracted case_titles). Fabrication check: a citation is valid
# only if its case_title contains at least one of these tokens.
LIVE_CORPUS = [
    "AMAECHI",
    "MADUKOLU",
    "ADEGOKE MOTORS",
    "ABACHA",
    "ADESANYA",
    "OBIKOYA",
    "AZUBUIKE",
    "ADEWUMI",
    "CHIKE OBI",
    "PABIEKUN",
    "ALIMI",
]


def _provisioned() -> tuple[bool, str]:
    s = get_settings()
    if not (s.anthropic_api_key or s.deepseek_api_key or s.openrouter_api_key):
        return False, "no answer-LLM credential (ANTHROPIC/DEEPSEEK/OPENROUTER)"
    if not (s.openai_api_key or s.openrouter_api_key or s.nvidia_api_key):
        return False, "no embedding credential (OPENAI / OPENROUTER / NVAPI)"
    if not s.database_url:
        return False, "DATABASE_URL not set"
    return True, ""


ok, reason = _provisioned()
pytestmark = pytest.mark.skipif(not ok, reason=f"citation battery deferred: {reason}")


def _load_battery() -> list[dict]:
    return json.loads(BATTERY_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("item", _load_battery(), ids=lambda i: i["id"])
async def test_battery(item: dict) -> None:
    """One battery entry: in-corpus questions must answer with verified,
    corpus-internal citations; out-of-corpus questions must refuse."""
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    try:
        await conn.execute(
            "SELECT set_config('app.tenant_id', $1, false)", SEED_TENANT
        )
        result = await answer_question(
            item["question"], item.get("filters") or {},
            conn, SEED_TENANT, "battery-runner", settings=settings,
        )
    finally:
        await conn.close()

    if item["expect"] == "refusal":
        assert result["refusal"] is True, (
            f"{item['id']}: out-of-corpus question produced an answer — "
            "possible confabulation"
        )
        assert result["citations"] == []
    else:
        assert result["refusal"] is False, f"{item['id']}: in-corpus question refused"
        assert result["citations"], f"{item['id']}: answer carried no citations"
        for cite in result["citations"]:
            # Fabrication = a citation to anything outside the live corpus.
            assert cite["verified"] is True
            assert any(
                token in cite["case_title"].upper() for token in LIVE_CORPUS
            ), f"{item['id']}: fabricated citation {cite['case_title']!r}"
            assert cite["page_start"] >= 1 and cite["page_end"] >= cite["page_start"]
