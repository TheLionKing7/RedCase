"""Chunker unit tests — Task 1.3 synthetic DoD.

Pins under test (Phase1-Design 2.2): page_start/page_end from page data,
paragraph_refs from numbered paragraphs, header chunk at index 0, windows
never split a paragraph, 512-token target with ~75-token overlap, ratio
tagging heuristic.
"""

import pymupdf

from app.ingestion.chunker import (
    Paragraph,
    chunk_document,
    chunk_pages,
    chunk_paragraphs,
    extract_paragraphs,
)
from tests.pdf_factory import make_pdf, synthetic_judgment_pages, synthetic_judgment_texts


def _p(num: int, start: int, end: int | None = None, text: str = "") -> Paragraph:
    p = Paragraph(num=num, start_page=start, end_page=end or start)
    p.parts.append(text or f"text of paragraph {num}")
    return p


class TestExtractParagraphs:
    def test_numbering_and_pages(self) -> None:
        paras = extract_paragraphs(synthetic_judgment_texts())
        # num=0 entries are the captured unnumbered caption block (u-refs).
        assert [p.num for p in paras] == [0, 1, 2, 3, 4, 5, 6]

    def test_unnumbered_prologue_captured(self) -> None:
        # Regression (2026-09-18): Madukolu pages 2-13 — all judgment prose
        # before the first numbered paragraph — existed in no chunk because
        # extract only walked numbered paragraphs. The page-1 caption lines
        # of the synthetic judgment must now appear as a u-block.
        paras = extract_paragraphs(synthetic_judgment_texts())
        u = [p for p in paras if p.ref]
        assert len(u) == 1
        assert u[0].ref == "u1"
        assert (u[0].start_page, u[0].end_page) == (1, 1)
        assert "SUPREME COURT" in u[0].text

    def test_cross_page_paragraph_tracks_end_page(self) -> None:
        paras = extract_paragraphs(synthetic_judgment_texts())
        p4 = next(p for p in paras if p.num == 4)
        assert p4.start_page == 2
        assert p4.end_page == 3  # continuation line lands on page 3

    def test_same_page_paragraph(self) -> None:
        paras = extract_paragraphs(synthetic_judgment_texts())
        p1 = next(p for p in paras if p.num == 1)
        assert (p1.start_page, p1.end_page) == (1, 1)


class TestChunkParagraphs:
    def test_oversized_paragraph_gets_own_chunk(self) -> None:
        big = _p(1, 1, text="word " * 600)  # ~600 tokens alone
        small = _p(2, 1)
        chunks = chunk_paragraphs([big, small], chunk_tokens=512, overlap_tokens=75)
        assert len(chunks) == 2
        assert chunks[0].paragraph_refs == ["1"]
        assert chunks[1].paragraph_refs == ["2"]

    def test_never_splits_mid_paragraph(self) -> None:
        paras = [_p(i, 1) for i in range(1, 21)]
        chunks = chunk_paragraphs(paras, chunk_tokens=20, overlap_tokens=5)
        first_seen: list[str] = []
        for c in chunks:
            assert c.paragraph_refs  # never empty
            for ref in c.paragraph_refs:
                if ref not in first_seen:
                    first_seen.append(ref)
        # Overlap may repeat refs across chunks, but first appearances must
        # cover every paragraph exactly once, in order.
        assert first_seen == [str(i) for i in range(1, 21)]

    def test_page_range_covers_constituent_paragraphs(self) -> None:
        paras = [_p(1, 1), _p(2, 3), _p(3, 3)]
        chunks = chunk_paragraphs(paras, chunk_tokens=512, overlap_tokens=75)
        assert len(chunks) == 1
        assert chunks[0].page_start == 1
        assert chunks[0].page_end == 3

    def test_overlap_carries_tail_paragraphs(self) -> None:
        # 6-token paragraphs, 20-token window, 10-token overlap (same
        # proportions as 2.2's 512/75 with typical paragraph sizes): after a
        # boundary, the next chunk must open with a paragraph from the tail.
        paras = [_p(i, 1, text="lorem ipsum dolor sit amet") for i in range(1, 11)]
        chunks = chunk_paragraphs(paras, chunk_tokens=20, overlap_tokens=10)
        assert len(chunks) >= 3
        for a, b in zip(chunks, chunks[1:], strict=False):
            assert b.paragraph_refs[0] in a.paragraph_refs  # overlap continuity

    def test_ratio_heuristic(self) -> None:
        plain = [_p(1, 1, text="plain reasoning"), _p(2, 1, text="more plain reasoning")]
        assert chunk_paragraphs(plain, chunk_tokens=512)[0].is_ratio is False
        mixed = [_p(1, 1, text="plain reasoning"), _p(2, 1, text="the Ratio decidendi is clear")]
        assert chunk_paragraphs(mixed, chunk_tokens=512)[0].is_ratio is True


class TestChunkDocument:
    def test_header_is_index_zero(self, tmp_path) -> None:
        pdf = make_pdf(tmp_path / "j.pdf", synthetic_judgment_pages())
        with pymupdf.open(pdf) as doc:
            chunks = chunk_document(doc)
        assert chunks[0].chunk_index == 0
        assert chunks[0].page_start == 1 and chunks[0].page_end == 1
        assert chunks[0].paragraph_refs == []
        assert "SUPREME COURT" in chunks[0].text
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_body_pins_match_extraction(self, tmp_path) -> None:
        pdf = make_pdf(tmp_path / "j.pdf", synthetic_judgment_pages())
        with pymupdf.open(pdf) as doc:
            pages = [p.get_text("text") for p in doc]
        paras = {p.num: p for p in extract_paragraphs(pages)}
        chunks = chunk_pages(pages)
        body = chunks[1:]
        for c in body:
            for ref in c.paragraph_refs:
                if not ref.isdigit():
                    continue  # unnumbered u-blocks have no Paragraph entry
                p = paras[int(ref)]
                assert c.page_start <= p.start_page, f"chunk {c.chunk_index} misses p{ref} start"
                assert c.page_end >= p.end_page, f"chunk {c.chunk_index} misses p{ref} end"
        # paragraph 4 starts on page 2 and ends on page 3
        p4 = next(p.num for p in paras.values() if p.start_page == 2 and p.end_page == 3)
        p4_chunk = next(c for c in body if str(p4) in c.paragraph_refs)
        assert p4_chunk.page_end == 3

    def test_ratio_flagged_in_body(self, tmp_path) -> None:
        pdf = make_pdf(tmp_path / "j.pdf", synthetic_judgment_pages())
        with pymupdf.open(pdf) as doc:
            chunks = chunk_document(doc)
        flagged = [c for c in chunks if c.is_ratio]
        assert flagged, "expected the ratio-decidendi passage to be flagged"
        assert any("Ratio decidendi" in c.text for c in flagged)
