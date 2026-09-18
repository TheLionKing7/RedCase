"""Battle Card + Claim Graph schemas — Phase3-Design §1.2 / §2.1, verbatim shapes.

These are the contracts every agent stage produces/consumes. The TypeScript
mirror lives in apps/web/src/lib/api/redteam.ts; drift between the two is a
design-doc violation (HANDOFF.md rule 3).
"""

from typing import Literal

from pydantic import BaseModel, Field


class Claim(BaseModel):
    id: str
    type: Literal["FACTUAL", "LEGAL", "PROCEDURAL"]
    text: str
    cited_authorities: list[str] = Field(default_factory=list)
    relief_sought: str = ""


class ClaimGraph(BaseModel):
    parties: dict[str, str] = Field(default_factory=dict)
    prayers: list[str] = Field(default_factory=list)
    procedural_history: list[str] = Field(default_factory=list)
    claims: list[Claim]
    notable_dates: list[str] = Field(default_factory=list)
    document_type: Literal["BRIEF", "MOTION", "AFFIDAVIT"]


class ProceduralFlaw(BaseModel):
    flaw: str
    basis: str
    authority: list[str] = Field(default_factory=list)
    severity: Literal["HIGH", "MED", "LOW"]
    confidence: float = Field(ge=0.0, le=1.0)


class OpposingArgument(BaseModel):
    argument: str
    strength: int = Field(ge=1, le=10)  # §1.2: 1-10, 10 = near-fatal to us
    our_counter: str
    authority: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    manual_review: bool = False


class BattleCardSections(BaseModel):
    procedural_flaws: list[ProceduralFlaw] = Field(default_factory=list)
    opposing_arguments: list[OpposingArgument] = Field(default_factory=list)
    jurisdictional_notes: list[str] = Field(default_factory=list)


class CriticVerdict(BaseModel):
    # `pass` is a Python keyword; the wire key stays "pass" (§1.2) via aliases.
    pass_: bool = Field(validation_alias="pass", serialization_alias="pass")
    regenerations: int = 0
    downgraded_sections: list[str] = Field(default_factory=list)


class BattleCard(BaseModel):
    # The Strategist only produces ``sections``; the engine composes the
    # envelope (document pin, timestamp, critic verdict) around them, so
    # these fields are engine-filled and default here. The §1.2 wire shape
    # is unaffected: every emitted card carries all three (engine contract).
    matter_id: str | None = None  # nullable until Phase 2 matters exist
    source_document_id: str = ""
    generated_at: str = ""
    sections: BattleCardSections
    critic_verdict: CriticVerdict = Field(
        default_factory=lambda: CriticVerdict(**{"pass": False})
    )


# ---------------------------------------------------------------------------
# Prompt-pack schemas — Feature-Addendum §3.3 (Step C). Both packs emit the
# §3.3 tab mapping "Overview, Arguments, Law" as ``sections``; the engine
# composes the same envelope (document pin, timestamp, critic verdict) as the
# battle card, so the /v1/analyses/{id} wire shape is uniform across packs.
# ---------------------------------------------------------------------------


class SummonsGraph(BaseModel):
    """Extractor output for SUMMONS_RESPONSE (§3.3: claims served)."""

    parties: dict[str, str] = Field(default_factory=dict)
    court: str = ""
    case_number: str = ""
    served_on: str = ""
    return_date: str = ""
    claims: list[Claim] = Field(default_factory=list)
    document_type: Literal["SUMMONS"]


class ServedClaim(BaseModel):
    """One served claim -> response deadline & strategy (§3.3)."""

    claim: str
    response_deadline: str = ""
    strategy: str = ""
    authority: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    manual_review: bool = False


class SummonsOverview(BaseModel):
    court: str = ""
    case_number: str = ""
    served_on: str = ""
    return_date: str = ""
    claimant: str = ""
    defendant: str = ""
    claims_served: int = 0
    headline_risks: list[str] = Field(default_factory=list)


class LawPoint(BaseModel):
    point: str
    authority: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)


class SummonsSections(BaseModel):
    overview: SummonsOverview
    arguments: list[ServedClaim] = Field(default_factory=list)
    law: list[LawPoint] = Field(default_factory=list)


class SummonsResponseOutput(BaseModel):
    matter_id: str | None = None
    source_document_id: str = ""
    generated_at: str = ""
    sections: SummonsSections
    critic_verdict: CriticVerdict = Field(
        default_factory=lambda: CriticVerdict(**{"pass": False})
    )


class ContractGraph(BaseModel):
    """Extractor output for CONTRACT_REVIEW (§3.3: clause extraction).

    Clauses reuse the Claim shape so the engine's per-claim retrieval loop
    is pack-agnostic; clause text carries the clause number and heading."""

    parties: dict[str, str] = Field(default_factory=dict)
    agreement_date: str = ""
    clauses: list[Claim] = Field(default_factory=list)
    document_type: Literal["CONTRACT"]


class ClauseFinding(BaseModel):
    """One clause -> risk flag + deviation note (§3.3)."""

    clause: str
    risk: Literal["LOW", "MED", "HIGH"]
    rationale: str
    deviation: str = ""  # vs firm standard template; Phase 2 Vault A router
    authority: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    manual_review: bool = False


class ContractOverview(BaseModel):
    parties: dict[str, str] = Field(default_factory=dict)
    agreement_date: str = ""
    clause_count: int = 0
    overall_risk: Literal["LOW", "MED", "HIGH"] = "LOW"
    headline_flags: list[str] = Field(default_factory=list)


class ContractSections(BaseModel):
    overview: ContractOverview
    arguments: list[ClauseFinding] = Field(default_factory=list)
    law: list[LawPoint] = Field(default_factory=list)


class ContractReviewOutput(BaseModel):
    matter_id: str | None = None
    source_document_id: str = ""
    generated_at: str = ""
    sections: ContractSections
    critic_verdict: CriticVerdict = Field(
        default_factory=lambda: CriticVerdict(**{"pass": False})
    )
