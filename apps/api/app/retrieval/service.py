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

import asyncio
import hashlib
import re
import time
import uuid
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

# The answer LLM occasionally echoes prompt scaffolding (<passages> /
# <question> / <filters> blocks) into its output — observed on DeepSeek
# battery runs 2026-09-18 (docs/calibration/phase1-jina.md, ZDR section).
# The scaffold is prompt body, not answer: strip any echoed block before
# verification and persistence. Deterministic, model-independent.
ECHO_BLOCK = re.compile(
    r"<(passages|question|filters)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)


def strip_echoed_blocks(text: str) -> str:
    """Remove echoed prompt-scaffold blocks from model output."""
    return ECHO_BLOCK.sub("", text).strip()
DEFAULT_TOP_K = 8  # presentation budget defaults; Settings overrides
DEFAULT_PER_DOC_CAP = 3
DEFAULT_RATIO_EXEMPT = False

CITATION_BLOCK = re.compile(r"<citations>(.*?)</citations>", re.S)
# The §3.2 prompt (rule 5) requires a <citations> block "listing every cited
# source document ID" but does not fix the list format; observed LLM outputs
# (DeepSeek, 2026-09-18) use bare UUID lines and <doc id="..."/> elements,
# never doc_id="..." attributes. Accept any UUID inside the block.
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)


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
        WHERE d.tenant_id = $1 AND v.vault_type = $8::text
          AND ($9::uuid IS NULL OR d.matter_id = $9)
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
        WHERE d.tenant_id = $1 AND v.vault_type = $8::text
          AND ($9::uuid IS NULL OR d.matter_id = $9)
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

# Vault A variant (Task 2.3/2.4): identical pipeline over firm documents.
# FTS degradation is EXPECTED for encrypted chunks (ciphertext indexes to
# garbage tokens; vector leg carries retrieval) — recorded in the 2.4 DoD
# report and the runbook backlog; the decrypt-then-index worker removes it.
HYBRID_SQL_FIRM = HYBRID_SQL


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


class RetrievalService:
    def __init__(self, db: asyncpg.Connection, tenant_id: str) -> None:
        self.db, self.tenant_id = db, tenant_id

    async def candidates(
        self,
        question: str,
        qvec: list[float],
        filters: dict[str, Any],
        *,
        threshold: float | None = None,
        vault: str = "juris",
    ) -> list[dict[str, Any]] | None:
        """Hybrid candidate fetch + the §3.4 refusal gate. Returns the raw
        hybrid-score-ordered rows, or None on refusal. Split from
        ``retrieve`` so gate calibration (scripts/calibrate_gate.py) can
        read the exact gate metric — the vsim of the top-hybrid-score row —
        without the presentation re-ordering below changing rows[0]."""
        # matter_id (Task 2.4): NULL means unfiltered — the Phase 1 juris path
        # never sets it, so its SQL shape is unchanged. Vault A dual-vault
        # retrieval sets it when a matter-scoped (non-partner) user asks.
        mid = filters.get("matter_id")
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
                "firm" if vault == "firm" else "juris",
                uuid.UUID(str(mid)) if mid else None,
            )
        ]
        # §3.4 refusal: no rows, or best vsim below the gate. NULL vsim
        # (deferred-embed chunks) is a threshold failure, not a crash.
        # The gate is settings-driven (Settings.vector_gate, calibrated
        # against the citation battery); the module constant is the
        # design-doc default for direct callers (tests) and the fallback.
        if not rows:
            return None
        best = rows[0]["vsim"]
        gate = SIMILARITY_THRESHOLD if threshold is None else threshold
        if best is None or best < gate:
            return None
        return rows

    async def retrieve(
        self,
        question: str,
        qvec: list[float],
        filters: dict[str, Any],
        *,
        threshold: float | None = None,
        top_k: int | None = None,
        per_doc_cap: int | None = None,
        ratio_exempt: bool | None = None,
        vault: str = "juris",
    ) -> list[dict[str, Any]] | None:
        rows = await self.candidates(
            question, qvec, filters, threshold=threshold, vault=vault
        )
        if rows is None:
            return None
        # Presentation budget (recorded adaptation, 2026-09-18): up to 8
        # passages, at most 3 per document. The old fixed top-5 let one
        # document's near-duplicate header chunks crowd out its own holding
        # chunk (found via B11: two Madukolu caption chunks ranked 1-2 while
        # the competence-dictum chunk sat 6th, and the answer LLM refused).
        # Passages are presented in vsim (semantic) order, not hybrid score
        # order: the hybrid weighting (0.35*fsim + ratio x1.3, §3.3) is a
        # recall-oriented SELECTOR, but as presentation order it buries the
        # on-point chunk. The gate metric (candidates' hybrid-top vsim) is
        # unaffected. NULL-vsim rows sort last.
        #
        # Budget knobs are config-driven (Settings.retrieval_top_k /
        # retrieval_per_doc_cap, passed in by answer_question); direct
        # callers get the module defaults. The 2026-09-18 gating matrix
        # sweeps these without code edits.
        budget_k = DEFAULT_TOP_K if top_k is None else top_k
        cap = DEFAULT_PER_DOC_CAP if per_doc_cap is None else per_doc_cap
        exempt = DEFAULT_RATIO_EXEMPT if ratio_exempt is None else ratio_exempt
        top: list[dict[str, Any]] = []
        per_doc: dict[Any, int] = {}
        for r in rows:
            n = per_doc.get(r["document_id"], 0)
            # Ratio chunks carry the holding; exempt them from the per-doc
            # cap so a document's own captions cannot crowd out its ratio.
            if n >= cap and not (exempt and r["is_ratio"]):
                continue
            per_doc[r["document_id"]] = n + 1
            top.append(r)
            if len(top) >= budget_k:
                break
        top.sort(key=lambda r: (r["vsim"] is not None, r["vsim"] or 0.0), reverse=True)
        return top

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
    block = CITATION_BLOCK.search(answer)
    # UUIDs anywhere inside the <citations> block: doc_id="..." attributes,
    # <doc id="..."/> elements, and bare UUID lines are all accepted.
    cited = UUID_RE.findall(block.group(1)) if block else []
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
    audit_extra: dict[str, Any] | None = None,
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
    rows = await svc.retrieve(
        question,
        qvec,
        filters,
        threshold=settings.vector_gate,
        top_k=settings.retrieval_top_k,
        per_doc_cap=settings.retrieval_per_doc_cap,
        ratio_exempt=settings.retrieval_ratio_exempt,
    )

    # audit_extra (Task 2.4): caller-supplied routing metadata (route,
    # route_confidence) folded into the persisted filters JSON — additive,
    # Phase 1 callers pass nothing and get the unchanged row shape.
    audit: dict[str, Any] = {
        "tenant_id": tenant_id,
        "user_ref": user_ref,
        "question_hash": hashlib.sha256(question.encode()).hexdigest(),
        "filters": {**filters, **(audit_extra or {})},
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
    base_audit: dict[str, Any] = dict(audit, threshold_passed=True)

    async def _answer_once() -> tuple[str, list[dict[str, Any]], int]:
        """One answer call with the §3.4 citation-integrity regeneration cap.
        Returns (answer_text, citations, regenerations_used). Raises
        CitationIntegrityError only when both passes fabricate a doc id —
        the caller then refuses, and the fabricated text is never shown or
        persisted."""
        system = GROUNDED_SYSTEM
        for regeneration in range(2):
            msg = strip_echoed_blocks(
                await asyncio.wait_for(
                    llm.answer(
                        system,
                        GROUNDED_USER.format(question=question, filters=filters, passages=passages),
                    ),
                    timeout=settings.answer_timeout_s,
                )
            )
            try:
                citations = verify_citations(
                    msg, rows, storage_public_url=settings.storage_public_url
                )
            except CitationIntegrityError:
                if regeneration == 0:
                    system = GROUNDED_SYSTEM + REGENERATION_SUFFIX
                    continue
                raise
            return CITATION_BLOCK.sub("", msg).strip(), citations, regeneration
        raise AssertionError("unreachable")  # noqa: EM101 (loop always returns/raises)

    # One-retry-on-refusal policy (owner-approved 2026-09-18, Task 1.7 step 1):
    # a grounding refusal triggers ONE retry of the same prompt. All
    # configured clients already answer at temperature 0, so the retry is an
    # identical deterministic call — the flapping it absorbs is server-side.
    # Integrity refusals do NOT retry here (that path already consumed its
    # one regeneration inside _answer_once). EVERY attempt writes its own
    # query_audit row (attempt 1 and, when reached, attempt 2), so per-attempt
    # refusal outcomes stay auditable.
    async def _audit_refusal(attempt: int, reason: str) -> None:
        """Log + audit ONE failed attempt. Refusal reasons are observability
        metadata in the structlog event only — the audit table deliberately
        stores refusal rows identically (answer_text NULL), keeping the
        append-only contract free of in-place-mutable columns."""
        await write_audit(
            db,
            _with_latency(dict(base_audit, answer_text=None, citations=[])),
        )
        log.info(
            "query_refused",
            reason=reason,
            attempt=attempt,
            question_hash=base_audit["question_hash"],
        )

    for attempt in (1, 2):
        try:
            answer, citations, regenerations = await _answer_once()
        except CitationIntegrityError as exc:
            # §3.4: second integrity failure -> refusal. A fabricated
            # citation is never shown to the user.
            await write_audit(
                db,
                _with_latency(
                    dict(
                        base_audit,
                        answer_text=None,
                        citations=[],
                        integrity_refusal=True,
                    )
                ),
            )
            log.warn(
                "query_refused",
                reason="citation_integrity",
                foreign_doc_id=str(exc),
                attempt=attempt,
                question_hash=base_audit["question_hash"],
            )
            return {
                "answer": "No binding precedent found in Vault B.",
                "citations": [],
                "refusal": True,
            }
        except TimeoutError:
            # answer_timeout_s ceiling: this attempt's answer call overran.
            # Logged as a refusal; the retry policy gets the one retry.
            await _audit_refusal(attempt, "answer_timeout")
            continue
        if not citations:
            # GROUNDED_SYSTEM rule 3 (§3.2): the LLM found the passages
            # unsupported and answered with the exact no-precedence sentence
            # and no <citations> block. Audit THIS attempt, then retry once.
            await _audit_refusal(attempt, "insufficient_grounding")
            continue
        await write_audit(
            db,
            _with_latency(
                dict(
                    base_audit,
                    answer_text=answer,
                    citations=citations,
                    retrieved_chunk_ids=[r["id"] for r in rows],
                    # NULL-vsim rows (deferred-embed chunks that rode along in
                    # the top-5 of an otherwise embedded corpus) contribute no
                    # score — skip them rather than float(None).
                    similarity_scores=[float(r["vsim"]) for r in rows if r["vsim"] is not None],
                    regenerations=regenerations,
                )
            ),
        )
        return {"answer": answer, "citations": citations, "refusal": False}

    # Both attempts refused on grounding.
    return {
        "answer": "No binding precedent found in Vault B.",
        "citations": [],
        "refusal": True,
    }
