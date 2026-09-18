"""Prompt-pack registry — Feature-Addendum §3.3 (Step C).

A prompt pack reuses the §2.1 four-agent skeleton (Extractor -> per-claim
retrieval -> Specialist -> Matcher -> Critic) with pack-specific extractor
and specialist prompts and a pack-specific output schema. The registry is
the single source of truth the /analyze endpoint validates against.

RECORDED (HANDOFF.md rule 3): §3.3's CONTRACT_REVIEW behaviour includes
"deviation from firm templates in Vault A". Vault A does not exist in
Phase 1 (no Phase 2 router), so the specialist is prompted to flag
deviations against standard-form conventions it knows and to LEAVE the
``deviation`` field empty (rather than invent one) when it has no template
to compare against. True Vault A template comparison swaps in with the
Phase 2 router; the field shape is already in the schema.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.redteam.engine import (
    CRITIC,
    EXTRACTOR,
    MATCHER,
    STRATEGIST,
)
from app.redteam.schemas import (
    BattleCard,
    ClaimGraph,
    ContractGraph,
    ContractReviewOutput,
    SummonsGraph,
    SummonsResponseOutput,
)

# ---------------------------------------------------------------------------
# Pack agent prompts. Only the Extractor and Specialist are pack-specific
# (§3.3: "different specialist prompts"); Matcher and Critic are shared —
# the matching/criticism contracts (verify-then-drop, kill-weak-analysis)
# are pack-agnostic by design.
# ---------------------------------------------------------------------------

SUMMONS_EXTRACTOR = """You are the RedCase Extractor. Analyze this served summons
and extract what was served. JSON only:
{"parties": {"claimant": "...", "defendant": "..."},
 "court": "...", "case_number": "...", "served_on": "YYYY-MM-DD",
 "return_date": "YYYY-MM-DD",
 "claims": [{"id": "c1", "type": "FACTUAL|LEGAL|PROCEDURAL",
             "text": "...", "cited_authorities": ["..."],
             "relief_sought": "..."}],
 "document_type": "SUMMONS"}
Rules: extract ONLY what the document states — every served claim with its
deadline exactly as stated, no inference, no strategy."""

SUMMONS_SPECIALIST = """You are a senior Nigerian litigation strategist (RedCase
Summons Response Specialist). Given the served-claim graph and retrieved
context, produce a response plan. For EACH served claim: the response
deadline exactly as extracted, our response strategy, and authority UUIDs
drawn ONLY from <context_uuids> that support the strategy. In ``law``, list
the procedural rules and authorities governing each response path.
JSON per the output schema. Authority UUIDs not in <context_uuids> are a
system failure."""

CONTRACT_EXTRACTOR = """You are the RedCase Extractor. Analyze this contract and
extract its clause structure. JSON only:
{"parties": {"party_a": "...", "party_b": "..."},
 "agreement_date": "YYYY-MM-DD",
 "clauses": [{"id": "c1", "type": "FACTUAL|LEGAL|PROCEDURAL",
              "text": "Clause N - Heading: operative text ...",
              "cited_authorities": [], "relief_sought": ""}],
 "document_type": "CONTRACT"}
Rules: extract ONLY what the document states. One entry per operative
clause, text prefixed with its clause number and heading; no commentary."""

CONTRACT_SPECIALIST = """You are a senior Nigerian commercial counsel (RedCase
Contract Review Specialist). Given the clause graph and retrieved context,
review each clause. For EACH clause: a risk flag (LOW/MED/HIGH), the
rationale, and authority UUIDs drawn ONLY from <context_uuids>. In
``deviation``, state the deviation from the conventional Nigerian
standard-form position for this clause type — leave it EMPTY when you have
no template basis to compare (do not invent one; Vault A template
comparison activates with the Phase 2 router). In ``law``, list the
statutes and authorities that drive the highest-risk flags.
JSON per the output schema. Authority UUIDs not in <context_uuids> are a
system failure."""


@dataclass(frozen=True)
class PromptPack:
    """One §3.3 prompt pack: prompts, schemas, and the section attribute
    names whose items carry ``authority`` lists for matcher verification
    and critic downgrading."""

    name: str
    extractor_prompt: str
    extractor_schema: type[BaseModel]
    specialist_prompt: str
    output_schema: type[BaseModel]
    match_sections: tuple[str, ...]


PACKS: dict[str, PromptPack] = {
    "ADVERSAL_BRIEF": PromptPack(
        name="ADVERSAL_BRIEF",
        extractor_prompt=EXTRACTOR,
        extractor_schema=ClaimGraph,
        specialist_prompt=STRATEGIST,
        output_schema=BattleCard,
        match_sections=("procedural_flaws", "opposing_arguments"),
    ),
    "SUMMONS_RESPONSE": PromptPack(
        name="SUMMONS_RESPONSE",
        extractor_prompt=SUMMONS_EXTRACTOR,
        extractor_schema=SummonsGraph,
        specialist_prompt=SUMMONS_SPECIALIST,
        output_schema=SummonsResponseOutput,
        match_sections=("arguments", "law"),
    ),
    "CONTRACT_REVIEW": PromptPack(
        name="CONTRACT_REVIEW",
        extractor_prompt=CONTRACT_EXTRACTOR,
        extractor_schema=ContractGraph,
        specialist_prompt=CONTRACT_SPECIALIST,
        output_schema=ContractReviewOutput,
        match_sections=("arguments", "law"),
    ),
}

# MATCHER/CRITIC kept importable here so the registry documents the shared
# stages without engine circularity (engine imports PACKS, not vice versa).
SHARED_AGENTS: dict[str, Any] = {"matcher": MATCHER, "critic": CRITIC}
