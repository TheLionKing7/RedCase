"""Deterministic metadata extraction for Vault B documents (Task 1.3).

Deterministic-first (Phase1-Design 4): regex over the judgment text. The
``--llm-assist`` pass (Phase 1.5 backlog) may fill ``ratio_decidendi`` /
``legal_topics`` later — never the reverse.
"""

import re
from dataclasses import dataclass

CITATION_RE = re.compile(r"\((\d{4})\)\s+(\d+)\s+NWLR\s*\(Pt\.\s*([\d\w]+)\)\s*(\d+)")
YEAR_FALLBACK_RE = re.compile(r"\b(19|20)\d{2}\b")
CASE_TITLE_RE = re.compile(r"^([A-Z][A-Z&'.\-() ]+? v\. [A-Z][A-Z&'.\-() ]+?)$", re.M)
CORAM_RE = re.compile(r"CORAM\s*[:\-]\s*([^\n]+)", re.I)
COURT_MAP = {
    "SUPREME COURT": "SUPREME_COURT",
    "COURT OF APPEAL": "COURT_OF_APPEAL",
    "FEDERAL HIGH COURT": "FEDERAL_HIGH_COURT",
    "STATE HIGH COURT": "STATE_HIGH_COURT",
    "NATIONAL INDUSTRIAL COURT": "NICN",
}


@dataclass(frozen=True)
class DocumentMetadata:
    case_title: str
    citation: str
    court_level: str
    year: int
    justices: list[str]
    metadata_confidence: float  # 0-1: how many heuristics fired cleanly


def _parse_citation(text: str, fallback_stem: str) -> tuple[str, int | None, bool]:
    m = CITATION_RE.search(text)
    if m:
        return m.group(0), int(m.group(1)), True
    return fallback_stem, None, False


def _parse_court(text_head: str) -> tuple[str, bool]:
    upper = text_head.upper()
    for k, v in COURT_MAP.items():
        if k in upper:
            return v, True
    return "STATUTE", False


def _parse_title(text: str, fallback_stem: str) -> tuple[str, bool]:
    m = CASE_TITLE_RE.search(text[:4000])
    if m:
        return " ".join(m.group(1).split()), True
    return fallback_stem, False


def _parse_coram(text: str) -> tuple[list[str], bool]:
    m = CORAM_RE.search(text[:4000])
    if not m:
        return [], False
    # Justices are semicolon-separated; commas belong to the names themselves
    # ("Musdapher, JSC") and must not be used as delimiters.
    block = re.split(r"\bAND\b", m.group(1), flags=re.I)[0]
    justices = [j.strip(" .") for j in block.split(";") if j.strip(" .")]
    return justices[:10], bool(justices)


def extract_metadata(text: str, fallback_stem: str) -> DocumentMetadata:
    """Extract document metadata. Raises ValueError when no year can be
    determined (documents.year is NOT NULL in 2.1; a document we cannot
    date is rejected rather than guessed)."""
    citation, year, citation_ok = _parse_citation(text, fallback_stem)
    if year is None:
        y = YEAR_FALLBACK_RE.search(text[:3000])
        if y:
            year = int(y.group(0))
        else:
            raise ValueError(
                f"No citation year or fallback year found for {fallback_stem!r}; "
                "refusing to ingest an undateable document."
            )
    court, court_ok = _parse_court(text[:3000])
    title, title_ok = _parse_title(text, fallback_stem)
    justices, coram_ok = _parse_coram(text)
    checks = (citation_ok, court_ok, title_ok, coram_ok)
    confidence = round(sum(checks) / len(checks), 2)
    return DocumentMetadata(
        case_title=title,
        citation=citation,
        court_level=court,
        year=year,
        justices=justices,
        metadata_confidence=confidence,
    )
