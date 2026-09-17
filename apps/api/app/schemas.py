"""API schemas — Phase1-Design §3.5, transcribed verbatim.

These are the wire contract for POST /v1/query; apps/web/src/lib/api/types.ts
is the TypeScript mirror. Any drift between the two is a design-doc violation
(HANDOFF.md rule 3) — report it, don't paper over it.
"""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=10, max_length=2000)
    court_level: str | None = None
    year_from: int | None = Field(None, ge=1960, le=2026)
    year_to: int | None = Field(None, ge=1960, le=2026)
    ratio_decidendi: str | None = None


class Citation(BaseModel):
    document_id: str
    case_title: str
    citation: str
    court_level: str
    year: int
    page_start: int
    page_end: int
    paragraph_refs: list[str]
    source_pdf_url: str
    verified: bool


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    refusal: bool
