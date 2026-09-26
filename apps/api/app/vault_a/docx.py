"""Bounded text extraction for uploaded Office Open XML documents.

DOCX is a ZIP container. Only the main document XML is read; external
relationships, macros, images, and embedded objects are never executed or
followed. Extracted text remains transient in worker memory, as with PDF
intake.
"""

from __future__ import annotations

from io import BytesIO
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

DOCX_MAIN_DOCUMENT = "word/document.xml"
MAX_DOCX_XML_BYTES = 10 * 1024 * 1024
MAX_DOCX_ENTRIES = 2_000
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class DocxError(ValueError):
    """Invalid, unsupported, or over-limit DOCX input."""


def extract_docx_text(raw: bytes) -> str:
    """Extract paragraph text from a bounded DOCX archive without persisting it."""
    try:
        with ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_ENTRIES:
                raise DocxError("DOCX contains too many archive entries")
            try:
                document = archive.getinfo(DOCX_MAIN_DOCUMENT)
            except KeyError as exc:
                raise DocxError("DOCX main document is missing") from exc
            if document.file_size > MAX_DOCX_XML_BYTES:
                raise DocxError("DOCX document text exceeds the size limit")
            xml = archive.read(document)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise DocxError("invalid DOCX archive") from exc

    if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
        raise DocxError("DOCX document XML declarations are not supported")
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise DocxError("invalid DOCX document XML") from exc

    paragraphs: list[str] = []
    for paragraph in root.iter(f"{WORD_NS}p"):
        parts = [node.text or "" for node in paragraph.iter(f"{WORD_NS}t")]
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    text = "\n".join(paragraphs).strip()
    if not text:
        raise DocxError("DOCX contains no extractable text")
    return text