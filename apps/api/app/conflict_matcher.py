"""Three-tier conflict matching (Addendum §9.1, task 3.9 sub-task 3).

Turns an incoming party name into a tiered judgement against a candidate name from a
conflict surface (CLIENT | MATTER | VAULT_A):

  EXACT   — normalized equivalence (score 1.0). normalization folds case/whitespace/
            punctuation and maps "&" -> "and", so "Adebayo & Co" ==
            "Adebayo and Company" is an exact match, not a fuzzy one. A party
            suffix formatted differently is STILL caught at the top tier.
  FUZZY   — token-aware similarity with a RECALL FLOOR (score >= 0.55), not
            just a ceiling. Uses the best of token-sequence similarity and same-position
            similarity, plus a shared-token bonus, so genuinely similar Nigerian party
            names ("Chukwuemeka" / "Emeka" is NOT a match — too little
            token overlap) surface with an explicit reason like
            "fuzzy match: 0.72 similarity + 2 shared tokens".
  PHONETIC- Soundex-homophone pairs as a FALLBACK only. It fires when an overall
            phonetic token-overlap justifies it ("Okechukwu" / "Okechukwu") and
            never as a naked homophone — pure Soundex on short names floods with false
            positives (the alarm-fatality failure the brief warns about). Requires >= 1
            shared normalized token so it corroborates rather than guesses.

Score semantics: 0..1; EXACT is always 1.0 and short-circuits. Candidates
below the FUZZY floor are dropped by the caller (they are noise, not candidates).

ZDR: party names are user/firm content and are stored on the check (they are the
screened work product — same class as a time entry description). They are never logged.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Literal

EXACT = Literal["EXACT"]
FUZZY = Literal["FUZZY"]
PHONETIC = Literal["PHONETIC"]
Tier = str

FUZZY_FLOOR = 0.55
_PHONETIC_TOP_TOKEN_SHARE = 0.5

# "&" is the canonical firm conjunction in Nigerian firm names; folding it to "and"
# makes differently-formatted suffixes ("A & Co" vs "A and Co") EXACT, which is
# precisely where a hard planted case should land.
_PUNCT_MAP = str.maketrans("&", " ", ".,'\"()[]{}:;!?-_|/\\")


def normalize(name: str) -> str:
    """Fold a party name to a comparable canonical form."""
    up = name.upper().translate(_PUNCT_MAP).replace("&", " AND ")
    return " ".join(up.split())


def _tokens(name: str) -> list[str]:
    return normalize(name).split()


def _soundex(token: str) -> str:
    """Classic four-character Soundex."""
    token = token.upper()
    if not token:
        return ""
    first = token[0]
    code = {"B": "1", "F": "1", "P": "1", "V": "1", "C": "2", "G": "2",
            "J": "2", "K": "2", "Q": "2", "S": "2", "X": "2", "Z": "2",
            "D": "3", "T": "3", "L": "4", "M": "5", "N": "5", "R": "6"}
    kept: list[str] = []
    prev = code.get(first, "")
    kept.append(prev)
    for ch in token[1:]:
        if ch in "AEIOUYHW":
            prev = ""
            continue
        c = code.get(ch, "")
        if c and c != prev:
            kept.append(c)
            prev = c
    return (first + "".join(kept)).ljust(4, "0")[:4]


def _fuzzy_score(a_tokens: list[str], b_tokens: list[str]) -> tuple[float, int]:
    """Token-aware similarity (0..1) + count of shared normalized tokens.

    Takes the best of whole-token-sequence similarity and same-position alignment, then
    blends in token-overlap so common firm words ("&"/"CO") don't dominate.
    """
    a = " ".join(a_tokens)
    b = " ".join(b_tokens)
    seq = SequenceMatcher(None, a, b).ratio()
    # position-aware: compare token by token
    pos = SequenceMatcher(None, a_tokens, b_tokens).ratio()
    shared = len(set(a_tokens) & set(b_tokens))
    best = max(seq, pos)
    overlap = (2.0 * shared) / (len(a_tokens) + len(b_tokens)) if a_tokens or b_tokens else 0.0
    combined = 0.75 * best + 0.25 * overlap
    return min(combined, 1.0), shared


def _phonetic_overlap(a_tokens: list[str], b_tokens: list[str]) -> tuple[float, int]:
    """Fraction of tokens that share a Soundex code + total shared-Soundex count."""
    ca = [_soundex(t) for t in a_tokens if _soundex(t)]
    cb = [_soundex(t) for t in b_tokens if _soundex(t)]
    if not ca or not cb:
        return 0.0, 0
    inter = len(set(ca) & set(cb))
    union = len(set(ca) | set(cb))
    return (inter / union if union else 0.0), inter


def match_party(party: str, candidate: str) -> tuple[Tier, float, list[str]]:
    """Classify `party` against `candidate`.

    Returns (tier, score, reasons). EXACT short-circuits at 1.0. FUZZY fires
    only at/above the recall floor. PHONETIC is a corroborated fallback.
    """
    pt = _tokens(party)
    ct = _tokens(candidate)
    if not pt or not ct:
        return FUZZY, 0.0, ["empty party name"]

    if " ".join(pt) == " ".join(ct):
        return "EXACT", 1.0, ["exact match after normalization"]

    fscore, fshared = _fuzzy_score(pt, ct)
    if fscore >= FUZZY_FLOOR and fshared >= 1:
        return "FUZZY", round(fscore, 4), [
            f"fuzzy match: {fscore:.2f} similarity + {fshared} shared token(s)"
        ]

    pscore, pshared = _phonetic_overlap(pt, ct)
    if (
        pscore >= _PHONETIC_TOP_TOKEN_SHARE
        and pshared >= 1
        and fshared >= 1  # must also share a literal token — corroborated, not guessed
    ):
        return "PHONETIC", round(pscore, 4), [
            f"phonetic match: {pshared} Soundex-homophone token(s) + corpus overlap"
        ]

    return FUZZY, round(fscore, 4), [
        f"below threshold: {fscore:.2f} similarity, {fshared} shared token(s)"
    ]
