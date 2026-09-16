"""Synthetic judgment PDF factory for chunker/ingestion tests.

Builds PDFs with known paragraph numbering and page breaks so tests can
assert exact page_start/page_end/paragraph_refs pins (Task 1.3 synthetic
DoD per owner instruction — corpus-dependent checks wait for ./fixtures).
"""

from pathlib import Path

import pymupdf


def make_pdf(path: Path, pages: list[list[str]], font_size: int = 11) -> Path:
    """pages: list of pages, each a list of text lines."""
    doc = pymupdf.open()
    for lines in pages:
        page = doc.new_page()
        page.insert_text((72, 72), "\n".join(lines), fontsize=font_size)
    doc.save(path)
    doc.close()
    return path


def synthetic_judgment_pages() -> list[list[str]]:
    """3-page SC judgment:
    page 1: court header, citation, title, coram, paragraphs 1-2
    page 2: paragraphs 3, 4 (4 contains the ratio marker)
    page 3: paragraph 4 continues (cross-page), paragraphs 5-6 (6 = "I hold that")
    """
    return [
        [
            "IN THE SUPREME COURT OF NIGERIA",
            "HOLDEN AT ABUJA",
            "FRIDAY, 12TH OCTOBER, 2007",
            "SUIT NO. SC.45/2006",
            "BETWEEN:",
            "ADESINA v. FEDERAL REPUBLIC",
            "NWLR CITATION: (2008) 5 NWLR (Pt. 1080) 227",
            "CORAM: Musdapher, JSC; Alooma, JSC; Kutigi, JSC",
            "1. This appeal borders on the interpretation of the Constitution.",
            "2. The facts are not in dispute and were set out by the court below.",
        ],
        [
            "3. The appellant contends that the trial court erred in law.",
            "4. The Ratio decidendi of this court is that statutory interpretation",
        ],
        [
            "on a constitutional question begins with the plain words of the text.",
            "5. Counsel cited ample authorities in support of this proposition.",
            "6. In conclusion, I hold that the appeal lacks merit and must fail.",
        ],
    ]


def synthetic_judgment_texts() -> list[str]:
    """Page texts as extract_pages() would return them."""
    return ["\n".join(lines) for lines in synthetic_judgment_pages()]
