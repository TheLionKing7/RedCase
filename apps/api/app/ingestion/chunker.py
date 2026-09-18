"""Page-tracked, paragraph-aligned chunker for Nigerian judicial judgments.

Implements Phase1-Design 2.2:
  * Case header  -> one fixed chunk per document (``chunk_index = 0``),
    always page 1, no paragraph refs.
  * Body         -> paragraph-aligned 512-token windows with ~75-token
    overlap (15%). Paragraphs are the atomic unit: a window never splits
    mid-sentence; an oversized paragraph becomes its own chunk.
  * Ratio        -> ``is_ratio = TRUE`` on passages matching the design's
    heuristic ("ratio decidendi" / "i hold that"), boosted later in scoring.
  * Pinning      -> ``page_start`` / ``page_end`` from PyMuPDF page data;
    ``paragraph_refs`` carries the numbered paragraph identifiers.

Deviation from design 4's illustrative code (recorded per HANDOFF rule 3):
body chunk indices start at 1 because the header owns index 0 (2.2's stated
contract); paragraph page ranges track paragraph *end* pages for paragraphs
that span a page break, instead of attributing them to the start page only.
Unnumbered prose before the first numbered paragraph is captured as
``u1``/``u2``/... blocks instead of being dropped (2.2's pseudocode only
walks numbered paragraphs; found 2026-09-18 — Madukolu pages 2-13, the
court's reasoning, existed in no chunk at all).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import pymupdf
import tiktoken

CHUNK_TOKENS = 512
OVERLAP_TOKENS = 75
HEADER_CHARS = 1500
# Unnumbered prose (judicial reasoning before the first numbered paragraph,
# e.g. Madukolu pages 2-13) is captured in blocks of at most this many
# lines so no single pseudo-paragraph swallows an entire section. Blocks
# extend to the next sentence-ending line (see flush_pending) — the 2.2
# atomicity contract applies to unnumbered prose too.
UNNUMBERED_BLOCK_LINES = 40
UNNUMBERED_LOOKAHEAD = 20  # max extra lines when hunting a sentence end

PARA_START_RE = re.compile(r"^(\d+)\.\s+(.*\S)\s*$")
END_SENTENCE_RE = re.compile(r"[.!?]['\")\]]*\s*$")
RATIO_MARKERS = ("ratio decidendi", "i hold that")

_encode: Callable[[str], list[int]] = tiktoken.get_encoding("cl100k_base").encode


@dataclass
class Paragraph:
    num: int
    start_page: int
    end_page: int
    parts: list[str] = field(default_factory=list)
    # Set for unnumbered prose blocks (captured before the first numbered
    # paragraph); paragraph_refs then carry this instead of str(num).
    ref: str | None = None

    @property
    def text(self) -> str:
        return " ".join(self.parts)

    @property
    def para_ref(self) -> str:
        return self.ref or str(self.num)


@dataclass
class Chunk:
    text: str
    chunk_index: int
    page_start: int
    page_end: int
    paragraph_refs: list[str]
    is_ratio: bool = False


def extract_pages(pdf: pymupdf.Document) -> list[str]:
    """Per-page plain text, 1 page per entry (index 0 = page 1)."""
    return [page.get_text("text") for page in pdf]


def extract_paragraphs(pages: list[str]) -> list[Paragraph]:
    """Numbered paragraphs with page pinning; continuations across a page
    break extend the paragraph's end_page.

    Unnumbered prose before the first numbered paragraph (or where no
    numbered paragraph has yet appeared) is captured too, in page-tracked
    blocks ref'd ``u1``, ``u2``, ... — previously it was silently dropped
    (found 2026-09-18: Madukolu pages 2-13, containing the judgment's
    reasoning, existed in no chunk at all). Unnumbered lines that FOLLOW a
    numbered paragraph still extend that paragraph (wrap/continuation
    lines), preserving the atomic-paragraph contract."""
    paras: list[Paragraph] = []
    cur: Paragraph | None = None
    pending: list[tuple[int, str]] = []  # (page_no, line) unnumbered prose
    unnumbered = 0

    def flush_pending() -> None:
        nonlocal unnumbered, pending
        i = 0
        while i < len(pending):
            j = min(i + UNNUMBERED_BLOCK_LINES, len(pending))
            if j < len(pending):
                # Atomicity (2.2): extend the block to the next line that
                # ends a sentence so chunk text never cuts mid-sentence
                # (found 2026-09-18 — a u-block ending mid-sentence made the
                # answer LLM distrust the corpus and over-refuse).
                limit = min(j + UNNUMBERED_LOOKAHEAD, len(pending))
                k = j
                while k < limit and not END_SENTENCE_RE.search(pending[k][1]):
                    k += 1
                j = k + 1 if k < limit else j
            block = pending[i:j]
            unnumbered += 1
            paras.append(
                Paragraph(
                    num=0,
                    start_page=block[0][0],
                    end_page=block[-1][0],
                    parts=[line for _, line in block],
                    ref=f"u{unnumbered}",
                )
            )
            i = j
        pending = []

    for i, text in enumerate(pages):
        page_no = i + 1
        for line in text.split("\n"):
            m = PARA_START_RE.match(line.strip()) if line.strip() else None
            if m:
                flush_pending()
                cur = Paragraph(num=int(m.group(1)), start_page=page_no, end_page=page_no)
                cur.parts.append(m.group(2))
                paras.append(cur)
            elif cur is None and line.strip():
                pending.append((page_no, line.strip()))
            elif cur is not None and line.strip():
                cur.parts.append(line.strip())
                cur.end_page = page_no
    flush_pending()
    return paras


def _make_chunk(buf: list[Paragraph], index: int) -> Chunk:
    text = "\n".join(f"{p.num}. {p.text}" for p in buf)
    return Chunk(
        text=text,
        chunk_index=index,
        page_start=min(p.start_page for p in buf),
        page_end=max(p.end_page for p in buf),
        paragraph_refs=[p.para_ref for p in buf],
        is_ratio=any(marker in text.lower() for marker in RATIO_MARKERS),
    )


def chunk_paragraphs(
    paras: list[Paragraph],
    chunk_tokens: int = CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    """Greedy paragraph packing into token windows with tail overlap.

    A paragraph that alone exceeds ``chunk_tokens`` is emitted as its own
    chunk (never split mid-sentence, 2.2)."""
    chunks: list[Chunk] = []
    buf: list[Paragraph] = []
    buf_tokens = 0
    for p in paras:
        p_tokens = len(_encode(p.text))
        if buf and buf_tokens + p_tokens > chunk_tokens:
            chunks.append(_make_chunk(buf, len(chunks)))
            carry: list[Paragraph] = []
            carry_tokens = 0
            for q in reversed(buf):
                q_tokens = len(_encode(q.text))
                if carry_tokens + q_tokens > overlap_tokens:
                    break
                carry.append(q)
                carry_tokens += q_tokens
            buf = list(reversed(carry))
            buf_tokens = carry_tokens
        buf.append(p)
        buf_tokens += p_tokens
    if buf:
        chunks.append(_make_chunk(buf, len(chunks)))
    return chunks


def chunk_pages(pages: list[str]) -> list[Chunk]:
    """Full chunking pipeline from extracted page texts: header chunk
    (index 0) + body chunks."""
    if not pages:
        raise ValueError("PDF has no pages")
    full_text = "\n".join(pages)
    header = Chunk(
        text=full_text[:HEADER_CHARS],
        chunk_index=0,
        page_start=1,
        page_end=1,
        paragraph_refs=[],
        is_ratio=False,
    )
    body = chunk_paragraphs(extract_paragraphs(pages))
    for c in body:
        c.chunk_index += 1
    return [header, *body]


def chunk_document(pdf: pymupdf.Document) -> list[Chunk]:
    """Convenience wrapper over an open PyMuPDF document."""
    return chunk_pages(extract_pages(pdf))
