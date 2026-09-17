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
