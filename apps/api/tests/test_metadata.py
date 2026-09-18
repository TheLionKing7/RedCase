"""Deterministic metadata extraction tests — Task 1.3."""

import pytest

from app.ingestion.metadata import extract_metadata

FULL_TEXT = """
IN THE SUPREME COURT OF NIGERIA
HOLDEN AT ABUJA
BETWEEN:
ADESINA v. FEDERAL REPUBLIC
NWLR CITATION: (2008) 5 NWLR (Pt. 1080) 227
CORAM: Musdapher, JSC; Alooma, JSC; Kutigi, JSC
1. This appeal borders on constitutional interpretation.
"""


class TestExtractMetadata:
    def test_full_header_extracts_cleanly(self) -> None:
        meta = extract_metadata(FULL_TEXT, "fallback")
        assert meta.citation == "(2008) 5 NWLR (Pt. 1080) 227"
        assert meta.year == 2008
        assert meta.court_level == "SUPREME_COURT"
        assert meta.case_title == "ADESINA v. FEDERAL REPUBLIC"
        assert meta.justices == ["Musdapher, JSC", "Alooma, JSC", "Kutigi, JSC"]
        assert meta.metadata_confidence == 1.0

    def test_court_of_appeal_mapping(self) -> None:
        text = FULL_TEXT.replace("SUPREME COURT OF NIGERIA", "COURT OF APPEAL")
        assert extract_metadata(text, "x").court_level == "COURT_OF_APPEAL"

    def test_missing_coram_lowers_confidence(self) -> None:
        text = FULL_TEXT.replace(
            "CORAM: Musdapher, JSC; Alooma, JSC; Kutigi, JSC\n", ""
        )
        meta = extract_metadata(text, "x")
        assert meta.justices == []
        assert meta.metadata_confidence == 0.75

    def test_no_citation_falls_back_to_year_in_text(self) -> None:
        text = (
            "IN THE SUPREME COURT OF NIGERIA\nBETWEEN:\nX v. Y\n"
            "1. This 1999 statute is clear.\n"
        )
        meta = extract_metadata(text, "Act-2004")
        assert meta.citation == "Act-2004"
        assert meta.year == 1999
        assert meta.court_level == "SUPREME_COURT"

    def test_undateable_document_rejected(self) -> None:
        with pytest.raises(ValueError, match="undateable"):
            extract_metadata("unstructured text with no dates at all", "x")

    def test_no_title_falls_back_to_stem(self) -> None:
        text = (
            "IN THE SUPREME COURT OF NIGERIA\n(2001) 2 NWLR (Pt. 100) 1\n"
            "CORAM: A, JSC\n1. text.\n"
        )
        meta = extract_metadata(text, "Stem Case")
        assert meta.case_title == "Stem Case"
        assert 0 < meta.metadata_confidence < 1


class TestMultiSeriesCitation:
    """Feature-Addendum §8 fallback: NWLR | SCNLR | All N.L.R. | ANLR | NGSC."""

    HEADER = "IN THE SUPREME COURT OF NIGERIA\nBETWEEN:\nX v. Y\n"

    def test_ngsc_neutral_citation(self) -> None:
        meta = extract_metadata(
            self.HEADER + "[1961] NGSC 28\nCORAM: A, JSC\n1. ratio.\n", "x"
        )
        assert meta.citation == "[1961] NGSC 28"
        assert meta.year == 1961

    def test_anlr(self) -> None:
        meta = extract_metadata(
            self.HEADER + "(1966) 1 ANLR 45\nCORAM: A, JSC\n1. ratio.\n", "x"
        )
        assert meta.citation == "(1966) 1 ANLR 45"
        assert meta.year == 1966

    def test_all_nlr_with_dots(self) -> None:
        meta = extract_metadata(
            self.HEADER + "(2005) 5 All N.L.R. 123\nCORAM: A, JSC\n1. ratio.\n", "x"
        )
        assert meta.citation == "(2005) 5 All N.L.R. 123"
        assert meta.year == 2005

    def test_scnlr(self) -> None:
        meta = extract_metadata(
            self.HEADER + "(2007) 12 SCNLR 89\nCORAM: A, JSC\n1. ratio.\n", "x"
        )
        assert meta.citation == "(2007) 12 SCNLR 89"
        assert meta.year == 2007

    def test_nwlr_wins_over_ngsc_when_both_present(self) -> None:
        text = (
            self.HEADER
            + "NWLR CITATION: (2008) 5 NWLR (Pt. 1080) 227\n"
            + "[1961] NGSC 28\nCORAM: A, JSC\n1. ratio.\n"
        )
        meta = extract_metadata(text, "x")
        assert meta.citation == "(2008) 5 NWLR (Pt. 1080) 227"

    def test_fallback_series_does_not_match_nwlr_text(self) -> None:
        # A bare "(1961)" year must not be swallowed as a partial series
        # citation; the year fallback still applies.
        meta = extract_metadata(
            self.HEADER + "Delivered in 1961.\nCORAM: A, JSC\n1. ratio.\n", "Stem"
        )
        assert meta.citation == "Stem"
        assert meta.year == 1961

    def test_citation_broken_across_lines_is_stored_single_line(self) -> None:
        """PDFs split citations at line breaks and \s matches newlines —
        the stored citation must be whitespace-normalized, not raw."""
        meta = extract_metadata(
            self.HEADER + "(1984)\n1 SCNLR 192\nCORAM: A, JSC\n1. ratio.\n", "x"
        )
        assert meta.citation == "(1984) 1 SCNLR 192"
        assert "\n" not in meta.citation
        assert meta.year == 1984
