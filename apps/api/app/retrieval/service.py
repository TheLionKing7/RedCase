"""Hybrid retrieval + grounding pipeline (Task 1.4/1.5, Phase1-Design §3.3/§3.4).

Adaptations from the design pseudocode, each recorded (HANDOFF.md rule 3):
  * SQLAlchemy ``text()``/``:named`` params -> asyncpg positional ``$n``
    (Tasks 1.2/1.3 standardised on asyncpg; the RLS GUC contract is
    ``set_config('app.tenant_id', ...)`` inside a transaction).
  * ``d.vault_type = 'juris'`` -> ``JOIN vaults v ... v.vault_type = 'juris'``
    (§2.1 DDL puts vault_type on vaults; §3.3's SQL referenced d.vault_type,
    which does not exist — §2.1 DDL is the schema of record and the live DB).
  * ``enrich_with_case_metadata`` (§3.5) is consolidated into the retrieval
    query: document fields are selected alongside chunk pins, so
    ``verify_citations`` emits complete Citation dicts in one pass. Same
    output contract.
  * NULL-vs-guard: chunks ingested with the deferred-embed path (Task 1.3)
    have embedding NULL; ``1 - (NULL <=> q)`` is NULL, and None < float would
    raise TypeError. NULL vsim is a threshold failure -> refusal, by design.

ZDR: no document text or question bodies in log lines — ids, counts, hashes.
"""

import hashlib
import re
import time
from typing import Any

import asyncpg

from app.config import Settings
from app.middleware.audit import write_audit
from app.middleware.zdr import get_logger
from app.retrieval.clients import AnswerLLM, Embedder, make_embedder, make_llm
from app.retrieval.prompts import (
    GROUNDED_SYSTEM,
    GROUNDED_USER,
    REGENERATION_SUFFIX,
)

log = get_logger("redcase.retrieval")

SIMILARITY_THRESHOLD = 0.78  # calibrated in Phase 1 testing; Phase1-Design §3.3

CITATION_BLOCK = re.compile(r"<citations>(.*?)</citations>", re.S)
DOC_ID = re.compile(r'doc_id="([^"]+)"')


class CitationIntegrityError(RuntimeError):
    """A cited doc_id was not in the retrieved set (Phase1-Design §3.4)."""


# Hybrid vector + FTS retrieval (§3.3 scoring: 0.65*vsim + 0.35*fsim, x1.3 for
# ratio passages), vault scoping via the vaults join (§2.1 DDL).
HYBRID_SQL = """
    WITH vec AS (
        SELECT dc.id, dc.document_id, dc.chunk_text, dc.page_start, dc.page_end,
               dc.paragraph_refs, dc.is_ratio,
               1 - (dc.embedding <=> $2::vector) AS vsim,
               d.case_title, d.citation, d.court_level, d.year, d.source_pdf_path
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        JOIN vaults v ON v.id = d.vault_id
        WHERE d.tenant_id = $1 AND v.vault_type = 'juris'
          AND ($3::text IS NULL OR d.court_level = $3)
          AND ($4::int IS NULL OR d.year >= $4)
          AND ($5::int IS NULL OR d.year <= $5)
          AND ($6::text IS NULL OR $6 = ANY(d.ratio_decidendi))
        ORDER BY dc.embedding <=> $2::vector
        LIMIT 40
    ),
    fts AS (
        SELECT dc.id,
               ts_rank(dc.fts, plainto_tsquery('english', $7)) AS fsim
        FROM document_chunks dc
        JOIN documents d ON d.id = dc.document_id
        JOIN vaults v ON v.id = d.vault_id
        WHERE d.tenant_id = $1 AND v.vault_type = 'juris'
          AND dc.fts @@ plainto_tsquery('english', $7)
        LIMIT 40
    )
    SELECT v.id, v.document_id, v.chunk_text, v.page_start, v.page_end,
           v.paragraph_refs, v.is_ratio, v.vsim,
           COALESCE(f.fsim, 0) AS fsim,
           (0.65 * v.vsim + 0.35 * COALESCE(f.fsim, 0))
             * CASE WHEN v.is_ratio THEN 1.3 ELSE 1.0 END AS score,
           v.case_title, v.citation, v.court_level, v.year, v.source_pdf_path
    FROM vec v LEFT JOIN fts f ON f.id = v.id
    ORDER BY score DESC NULLS LAST
    LIMIT 20
"""


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


class RetrievalService:
    def __init__(self, db: asyncpg.Connection, tenant_id: str) -> None:
        self.db, self.tenant_id = db, tenant_id

    async def retrieve(
        self, question: str, qvec: list[float], filters: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        rows = [
            dict(r)
            for r in await self.db.fetch(
                HYBRID_SQL,
                self.tenant_id,
                _vec_literal(qvec),
                filters.get("court_level"),
                filters.get("year_from"),
                filters.get("year_to"),
                filters.get("ratio_decidendi"),
                question,
            )
        ]
        # §3.4 refusal: no rows, or best vsim below the gate. NULL vsim
        # (deferred-embed chunks) is a threshold failure, not a crash.
        if not rows:
            return None
        best = rows[0]["vsim"]
        if best is None or best < SIMILARITY_THRESHOLD:
            return None
        return rows[:5]

    @staticmethod
    def build_passages(rows: list[dict[str, Any]]) -> str:
        return "\n\n".join(
            f'<passage doc_id="{r["document_id"]}" pages="{r["page_start"]}-{r["page_end"]}" '
            f'paras="{",".join(r["paragraph_refs"] or [])}" ratio="{r["is_ratio"]}">\n'
            f'{r["chunk_text"]}\n</passage>'
            for r in rows
        )


def verify_citations(
    answer: str, rows: list[dict[str, Any]], *, storage_public_url: str | None = None
) -> list[dict[str, Any]]:
    """Post-generation guard (§3.4, verbatim behaviour): cited doc_ids must
    exist in the retrieved set, and every citation carries the chunk's
    page/paragraph pins. Raises CitationIntegrityError on any foreign id —
    the caller regenerates once, then refuses."""
    valid_ids = {str(r["document_id"]) for r in rows}
    row_by_doc = {str(r["document_id"]): r for r in rows}
    cited = DOC_ID.findall(answer)
    citations = []
    for doc_id in dict.fromkeys(cited):  # dedupe, preserve order
        if doc_id not in valid_ids:
            raise CitationIntegrityError(doc_id)
        r = row_by_doc[doc_id]
        pdf = r["source_pdf_path"]
        citations.append(
            {
                "document_id": doc_id,
                "case_title": r["case_title"],
                "citation": r["citation"],
                "court_level": r["court_level"],
                "year": r["year"],
                "page_start": r["page_start"],
                "page_end": r["page_end"],
                "paragraph_refs": [str(p) for p in (r["paragraph_refs"] or [])],
                "source_pdf_url": f"{storage_public_url}/{pdf}" if storage_public_url else pdf,
                "verified": True,
            }
        )
    return citations


async def answer_question(
    question: str,
    filters: dict[str, Any],
    db: asyncpg.Connection,
    tenant_id: str,
    user_ref: str,
    *,
    settings: Settings,
    embedder: Embedder | None = None,
    llm: AnswerLLM | None = None,
) -> dict[str, Any]:
    """Grounded answer pipeline (§3.3) with the §3.4 refusal contracts and
    the one-regeneration cap. ``embedder``/``llm`` are injectable for tests;
    production defaults resolve from settings (503 when unprovisioned)."""
    embedder = embedder or make_embedder(settings)
    llm = llm or make_llm(settings)
    started = time.monotonic()

    def _with_latency(payload: dict[str, Any]) -> dict[str, Any]:
        payload["latency_ms"] = int((time.monotonic() - started) * 1000)
        return payload

    svc = RetrievalService(db, tenant_id)
    qvec = (await embedder.embed([question]))[0]
    rows = await svc.retrieve(question, qvec, filters)

    audit: dict[str, Any] = {
        "tenant_id": tenant_id,
        "user_ref": user_ref,
        "question_hash": hashlib.sha256(question.encode()).hexdigest(),
        "filters": filters,
    }

    if rows is None:
        audit.update(threshold_passed=False, answer_text=None, citations=[])
        await write_audit(db, _with_latency(audit))
        log.info("query_refused", reason="threshold", question_hash=audit["question_hash"])
        return {
            "answer": "No binding precedent found in Vault B.",
            "citations": [],
            "refusal": True,
        }

    passages = svc.build_passages(rows)
    system = GROUNDED_SYSTEM
    answer: str | None = None
    citations: list[dict[str, Any]] = []
    regenerations = 0
    while True:
        msg = await llm.answer(
            system,
            GROUNDED_USER.format(question=question, filters=filters, passages=passages),
        )
        try:
            citations = verify_citations(
                msg, rows, storage_public_url=settings.storage_public_url
            )
            answer = CITATION_BLOCK.sub("", msg).strip()
            break
        except CitationIntegrityError as exc:
            regenerations += 1
            if regenerations > 1:
                # §3.4: second failure -> refusal. A fabricated citation is
                # never shown to the user.
                audit.update(
                    threshold_passed=True,
                    answer_text=None,
                    citations=[],
                    integrity_refusal=True,
                )
                await write_audit(db, _with_latency(audit))
                log.warn(
                    "query_refused",
                    reason="citation_integrity",
                    foreign_doc_id=str(exc),
                    question_hash=audit["question_hash"],
                )
                return {
                    "answer": "No binding precedent found in Vault B.",
                    "citations": [],
                    "refusal": True,
                }
            system = GROUNDED_SYSTEM + REGENERATION_SUFFIX

    audit.update(
        threshold_passed=True,
        answer_text=answer,
        citations=citations,
        retrieved_chunk_ids=[r["id"] for r in rows],
        # NULL-vsim rows (deferred-embed chunks that rode along in the top-5
        # of an otherwise embedded corpus) contribute no score — skip them
        # rather than float(None).
        similarity_scores=[float(r["vsim"]) for r in rows if r["vsim"] is not None],
        regenerations=regenerations,
    )
    await write_audit(db, _with_latency(audit))
    return {"answer": answer, "citations": citations, "refusal": False}
