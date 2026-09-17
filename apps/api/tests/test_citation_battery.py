"""50-question citation battery — Task 1.5 corpus-dependent DoD.

DoD contract (HANDOFF.md 4 / Phase1-Design 3.4): run the battery against the
10 benchmark Supreme Court PDFs in ./fixtures; ZERO fabricated citations
allowed — every returned citation must be page-pinned to a retrieved chunk,
and out-of-corpus questions must produce refusals, not confabulation.

STATUS: DEFERRED-PENDING-CREDENTIALS (owner-approved path, 2026-09-16).
The corpus is live in Supabase (Task 1.3) but embeddings are NOT backfilled
(OpenRouter 402 / HF 401 / no OpenAI or Anthropic key), and the answer LLM
is unprovisioned — so this module SKIPS unless both exist. When provisioned:

  1. Backfill embeddings:  python -m scripts.ingest --fixtures-dir <dir>
     (re-run WITHOUT --no-embed; idempotent sha256 dedup skips text rows and
     fills only the NULL embeddings)
  2. Calibrate VECTOR_GATE against the battery, then
  3. Run:  pytest tests/test_citation_battery.py -v

The starter question set below is a DRAFT (10 of 50) written against the 8
judgments confirmed live; it must be reviewed and expanded to the full 50
when the battery is first run for real.
"""

import json
from pathlib import Path

import asyncpg
import pytest

from app.config import Settings
from app.retrieval.service import answer_question

BATTERY_PATH = Path(__file__).parent / "fixtures" / "citation_battery.json"
SEED_TENANT = "a0000001-0000-4000-8000-000000000001"

# Judgments confirmed ingested in the live vault (Task 1.3 commit 7fc0037).
LIVE_CORPUS = [
    "Amaechi v. INEC",
    "Madukolu v. Nkemdilim",
    "Adegoke Motors v. Adesanya",
    "Abacha v. Fawehinmi",
    "Adesanya v. FRN",
    "Obikoya v. Wema Bank",
    "Azubuike",
    "Ondo State Gov v. Adewumi",
]


def _provisioned() -> tuple[bool, str]:
    s = Settings(_env_file=None)
    if not s.anthropic_api_key:
        return False, "ANTHROPIC_API_KEY not provisioned (answer LLM)"
    if not (s.openai_api_key or s.openrouter_api_key):
        return False, "no embedding credential (OPENAI_API_KEY / OPENROUTER_API_KEY)"
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
    settings = Settings(_env_file=None)
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
                cite["case_title"].startswith(name.split(" v. ")[0])
                for name in LIVE_CORPUS
            ), f"{item['id']}: fabricated citation {cite['case_title']!r}"
            assert cite["page_start"] >= 1 and cite["page_end"] >= cite["page_start"]
