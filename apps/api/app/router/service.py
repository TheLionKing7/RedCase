"""Dual-vault query router — Phase2-Design §2.2 with the Phase 1 codebase's
real contracts, plus refusal semantics per Phase3-Design §0.

Adaptations from the §2.2 pseudocode, each recorded (HANDOFF.md rule 3):
  * ``zdr_client.anthropic()`` / AsyncAnthropic -> the env-selectable
    provider chain (``make_llm``, owner ruling: Groq/Cerebras capacity-
    blocked, provisioned chain with DeepSeek acceptable for the classifier —
    classifier questions are short and it never sees document content, so
    it adds no privilege surface either way).
  * SQLAlchemy AsyncSession -> asyncpg connection (Tasks 1.2/1.3 standard).
  * ``RetrievalService(db, tenant_id, user_ref=..., clearance=...,
    vault=...)`` constructor kwargs -> the Phase 1 constructor
    ``RetrievalService(db, tenant_id)`` with ``vault``/filters as call-time
    params (Task 2.3 shape). RLS is unchanged: the request connection
    carries app.tenant_id / app.user_ref / app.user_clearance GUCs set by
    deps.get_tenant_context, and the Vault A policies read them in SQL —
    a code path that forgets the filter cannot exist, because the filter
    is the policy (§2.2 key decision, preserved verbatim in behavior).
  * ``ctx.matter_id`` on TenantContext -> an explicit ``matter_id`` argument
    (TenantContext stays a request-scoped auth object; matter binding is a
    query-planner concern, per §2.2 "Route-A + matter binding").
  * §2.2's ``audit_extra`` on answer_question did not exist in Phase 1 ->
    added as an additive param folded into the persisted filters JSON.
  * Route-A + matter binding ruling implemented as designed: a matter_id
    pre-filters Vault A retrieval UNLESS the user's clearance is
    PARTNER/ADMIN (cross-matter clearance), matching how firms compartmentalize.
  * Single-attempt synthesis: the Phase 1 one-retry-on-refusal policy lives
    inside answer_question (route B reuses it verbatim); the A/BOTH
    synthesis path records its refusal and stops — DoD for 2.4 does not
    extend the retry policy across namespaces, and a fabricated citation
    is never shown regardless.
  * §2.2's ``asyncio.gather`` parallel retrieval -> sequential awaits on
    the request's single asyncpg connection (asyncpg connections are not
    concurrent-safe; two in-flight fetches raise InterfaceError). The
    RLS/privilege contract is identical; only latency overlap is lost.
    Marked at the call site.

Refusal semantics (Phase3 §0), implemented as the ``mode`` argument:
  STRICT    — miss -> refusal (route B via answer_question; A/BOTH below).
  ADVISORY  — label low-confidence, continue (Red-Teamer battle cards;
              supported here for completeness, unused by /v1/dual/query).
  HYBRID    — refuse on unsupported legal propositions, label strategic
              analysis (cross-vault synthesis; the endpoint default):
              * Vault A miss + Vault B miss  -> refusal, never a guess.
              * Vault A hit + Vault B miss   -> internal-only answer,
                explicitly labeled "Internal strategy — no public
                authority found." (§2.2 refusal semantics, verbatim).
              * Vault A miss + Vault B hit   -> public-authority answer,
                labeled as such.
              * both hit                     -> SYNTH_SYSTEM synthesis.

Citation namespaces: [A:doc_id, p.X] for firm documents, [B:doc_id, ...]
for jurisprudence. verify_namespaced_citations enforces at the SQL-id
level that an [A:...] citation resolves to a retrieved FIRM row and a
[B:...] citation to a retrieved JURIS row; a foreign id in either slot
raises CitationIntegrityError (Phase 1 §3.4 contract) and the call
refuses — zero fabricated citations is a hard gate.

ZDR: classifier and synthesis prompts/questions never enter log lines or
persisted rows beyond the question SHA-256 and metadata (route, counts).

FTS degradation (recorded in the 2.3 commit + runbook backlog): Vault A
retrieval over encrypted (CONFIDENTIAL+) chunks is vector-only — the fts
leg indexes ciphertext. Expected Phase 2 behavior; the decrypt-then-index
worker removes it.
"""

import asyncio
import hashlib
import json
import re
import time
from enum import StrEnum
from typing import Any

import asyncpg

from app.config import Settings
from app.middleware.audit import write_audit
from app.middleware.zdr import get_logger
from app.retrieval.clients import AnswerLLM, Embedder, make_embedder, make_llm
from app.retrieval.service import (
    CITATION_BLOCK,
    CitationIntegrityError,
    RetrievalService,
    answer_question,
    strip_echoed_blocks,
)
from app.vault_a.crypto import KeyProvider, decrypt_chunk_text, make_key_provider

log = get_logger("redcase.router")

# §2.2 route contract, verbatim text (source of truth: Phase2-Design §2.2).
ROUTER_SYSTEM = """Classify the legal query into exactly one route.
A = firm-internal knowledge (our past briefs, strategy, templates, matters).
B = public Nigerian law (statutes, case precedent) — the answer exists in public sources.
BOTH = drafting/synthesis that needs our internal approach AND public authority.
Reply with JSON only: {"route": "A"|"B"|"BOTH", "confidence": 0.0-1.0,
"rewritten_queries": {"a": "...", "b": "..."}}  — rewrite per-vault queries for
best retrieval. If confidence < 0.6, use route B."""

# §2.2 SYNTH_SYSTEM, verbatim modulo line-wrapping (the design's single
# long line 1 is wrapped mid-sentence; whitespace-only change, recorded per
# HANDOFF.md rule 3). Namespace rules 1-4 are the contract
# verify_namespaced_citations enforces afterwards.
SYNTH_SYSTEM = """You are RedCase cross-vault synthesis. Two citation namespaces:
<internal> passages = Vault A firm documents (cite: [A:doc_id, p.X]).
<public> passages = Vault B jurisprudence (cite: [B:doc_id, citation, p.X, ¶Y (Justice)]).
Rules:
1. Internal strategy informs STRUCTURE and ARGUMENT; public authority provides
LEGAL GROUNDING. Never present internal position as public law or vice versa.
2. Every proposition carries a namespace-tagged citation. No namespace mixing.
3. Unsupported by either namespace → "No binding support found."
4. End with <citations> listing both sets separately."""

INTERNAL_ONLY_LABEL = "Internal strategy — no public authority found."
PUBLIC_ONLY_LABEL = "Public authority only — no internal strategy found."

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
NS_REF = {
    "A": re.compile(rf"\[A:\s*({_UUID})", re.IGNORECASE),
    "B": re.compile(rf"\[B:\s*({_UUID})", re.IGNORECASE),
}
UUID_ANY = re.compile(_UUID, re.IGNORECASE)

# Clearances with cross-matter visibility (§2.2 matter-binding ruling).
_CROSS_MATTER = ("PARTNER", "ADMIN")


class Route(StrEnum):
    VAULT_A = "A"
    VAULT_B = "B"
    BOTH = "BOTH"


class Mode(StrEnum):
    STRICT = "STRICT"
    ADVISORY = "ADVISORY"
    HYBRID = "HYBRID"


def extract_json(text: str) -> str:
    """Isolate the first JSON object in the model output (tolerates prose
    wrappers and ```json fences, per the Phase 1 prompt-body observations)."""
    fence = _JSON_FENCE.search(text)
    if fence:
        return fence.group(1).strip()
    start, depth, in_str, esc = -1, 0, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start : i + 1]
    return text


async def classify(question: str, llm: AnswerLLM) -> dict[str, Any]:
    """§2.2 classify(): one cheap LLM call, question only (never document
    content — no privilege surface). Parse failure or confidence < 0.6
    degrades to route B, the public-law default (never A: degrading into
    the firm vault would widen the privilege surface on a bad parse)."""
    raw = await llm.answer(ROUTER_SYSTEM, question)
    try:
        plan = json.loads(extract_json(raw))
    except (json.JSONDecodeError, ValueError):
        plan = {"route": "B", "confidence": 0.0}
    route = str(plan.get("route", "B")).upper()
    if route not in (Route.VAULT_A, Route.VAULT_B, Route.BOTH):
        route = Route.VAULT_B
    try:
        confidence = float(plan.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < 0.6:
        route = Route.VAULT_B
    rewritten = plan.get("rewritten_queries")
    if not isinstance(rewritten, dict):
        rewritten = {}
    return {
        "route": route,
        "confidence": confidence,
        "rewritten_queries": {
            "a": str(rewritten.get("a") or question),
            "b": str(rewritten.get("b") or question),
        },
    }


async def _retrieve(
    question: str,
    conn: asyncpg.Connection,
    tenant_id: str,
    settings: Settings,
    embedder: Embedder,
    *,
    vault: str,
    filters: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Retrieval-only leg (dry_run in §2.2 terms): same knobs as
    answer_question, no generation, no audit — the caller audits once."""
    svc = RetrievalService(conn, tenant_id)
    qvec = (await embedder.embed([question]))[0]
    return await svc.retrieve(
        question,
        qvec,
        filters,
        threshold=settings.vector_gate,
        top_k=settings.retrieval_top_k,
        per_doc_cap=settings.retrieval_per_doc_cap,
        ratio_exempt=settings.retrieval_ratio_exempt,
        vault=vault,
    )


async def _decrypt_rows(
    rows: list[dict[str, Any]],
    conn: asyncpg.Connection,
    provider: KeyProvider,
) -> list[dict[str, Any]]:
    """Decrypt-on-retrieve for Vault A rows (§2.2 vault_a_query): unwrap each
    document's DEK once, decrypt enc:v1 chunk text in memory. Stored rows
    stay ciphertext; plaintext never leaves this function except inside the
    prompt body built from it (ZDR: never logged)."""
    if not rows:
        return rows
    ids = list({r["document_id"] for r in rows})
    key_rows = await conn.fetch(
        "SELECT id, dek_wrapped FROM documents WHERE id = ANY($1::uuid[])", ids
    )
    deks = {
        r["id"]: (
            provider.unwrap(r["dek_wrapped"], str(r["id"]).encode())
            if r["dek_wrapped"] is not None
            else None
        )
        for r in key_rows
    }
    out = []
    for r in rows:
        r = dict(r)
        dek = deks.get(r["document_id"])
        if dek is not None:
            aad = str(r["document_id"]).encode()
            r["chunk_text"] = decrypt_chunk_text(dek, r["chunk_text"], aad)
        out.append(r)
    return out


def _namespaced_passages(rows: list[dict[str, Any]], ns: str) -> str:
    return "\n\n".join(
        f'<passage ns="{ns}" doc_id="{r["document_id"]}" '
        f'pages="{r["page_start"]}-{r["page_end"]}" '
        f'paras="{",".join(r["paragraph_refs"] or [])}" ratio="{r["is_ratio"]}">\n'
        f'{r["chunk_text"]}\n</passage>'
        for r in rows
    )


def verify_namespaced_citations(
    answer: str,
    a_rows: list[dict[str, Any]],
    b_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Namespace-mixing guard (§2.2 rule 2 + §3.4 integrity contract):
    every [A:uuid] resolves to a retrieved FIRM row, every [B:uuid] to a
    retrieved JURIS row; bare UUIDs inside the <citations> block must belong
    to the union. A foreign id in any slot raises CitationIntegrityError —
    the caller refuses, and the fabricated text is never shown."""
    rows_by_ns = {"A": a_rows, "B": b_rows}
    ids_by_ns = {
        ns: {str(r["document_id"]) for r in rows} for ns, rows in rows_by_ns.items()
    }
    union = ids_by_ns["A"] | ids_by_ns["B"]
    citations: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for ns, pattern in NS_REF.items():
        for m in pattern.finditer(answer):
            doc_id = m.group(1).lower()
            if doc_id not in ids_by_ns[ns]:
                raise CitationIntegrityError(
                    f"[{ns}:{doc_id}] is not in the retrieved {ns} set"
                )
            if (ns, doc_id) in seen:
                continue
            seen.add((ns, doc_id))
            row = next(r for r in rows_by_ns[ns] if str(r["document_id"]) == doc_id)
            citations.append(
                {
                    "namespace": ns,
                    "ref": f"{ns}:{doc_id}",
                    "document_id": doc_id,
                    "case_title": row["case_title"],
                    "citation": row["citation"],
                    "court_level": row["court_level"],
                    "year": row["year"],
                    "page_start": row["page_start"],
                    "page_end": row["page_end"],
                    "paragraph_refs": [str(p) for p in (row["paragraph_refs"] or [])],
                    "verified": True,
                }
            )
    block = CITATION_BLOCK.search(answer)
    if block:
        for bare in UUID_ANY.findall(block.group(1)):
            if bare.lower() not in union:
                raise CitationIntegrityError(
                    f"citations block references unretrieved doc {bare}"
                )
    return citations


async def _synthesize(
    question: str,
    *,
    a_rows: list[dict[str, Any]],
    b_rows: list[dict[str, Any]],
    llm: AnswerLLM,
    settings: Settings,
) -> tuple[str, list[dict[str, Any]]]:
    """One synthesis call (§2.2 SYNTH_SYSTEM) + namespace verification.
    Returns (answer_text, citations); CitationIntegrityError propagates."""
    blocks = [f"<question>{question}</question>"]
    if a_rows:
        blocks.append(f"<internal>{_namespaced_passages(a_rows, 'A')}</internal>")
    if b_rows:
        blocks.append(f"<public>{_namespaced_passages(b_rows, 'B')}</public>")
    msg = strip_echoed_blocks(
        await asyncio.wait_for(
            llm.answer(SYNTH_SYSTEM, "\n".join(blocks)),
            timeout=settings.answer_timeout_s,
        )
    )
    citations = verify_namespaced_citations(msg, a_rows, b_rows)
    return CITATION_BLOCK.sub("", msg).strip(), citations


def _label_internal(answer: str) -> str:
    if INTERNAL_ONLY_LABEL.lower() in answer.lower():
        return answer
    return f"{INTERNAL_ONLY_LABEL}\n\n{answer}"


def _label_public(answer: str) -> str:
    if PUBLIC_ONLY_LABEL.lower() in answer.lower():
        return answer
    return f"{PUBLIC_ONLY_LABEL}\n\n{answer}"


async def dual_vault_query(
    *,
    question: str,
    conn: asyncpg.Connection,
    tenant_id: str,
    user_ref: str,
    clearance: str,
    settings: Settings,
    matter_id: str | None = None,
    mode: Mode | str = Mode.HYBRID,
    embedder: Embedder | None = None,
    llm: AnswerLLM | None = None,
    provider: KeyProvider | None = None,
) -> dict[str, Any]:
    """§2.2 dual_vault_query against the Phase 1 contracts.

    Writes exactly one query_audit row per call (refusals included), on the
    caller's RLS-scoped connection. Route B delegates to answer_question,
    which owns its own audit row — never two rows for one question."""
    embedder = embedder or make_embedder(settings)
    llm = llm or make_llm(settings)
    provider = provider or make_key_provider(settings)
    mode = Mode(str(mode).upper())
    started = time.monotonic()

    plan = await classify(question, llm)
    route, confidence = plan["route"], plan["confidence"]
    log.info("route_decision", route=route, confidence=confidence, tenant_id=tenant_id)

    def _latency(payload: dict[str, Any]) -> dict[str, Any]:
        payload["latency_ms"] = int((time.monotonic() - started) * 1000)
        return payload

    async def _audit(payload: dict[str, Any]) -> None:
        await write_audit(
            conn,
            _latency(
                dict(
                    {
                        "tenant_id": tenant_id,
                        "user_ref": user_ref,
                        "question_hash": hashlib.sha256(
                            question.encode()
                        ).hexdigest(),
                        "filters": {
                            "dual": True,
                            "route": route,
                            "route_confidence": confidence,
                            "mode": mode.value,
                            "matter_id": matter_id,
                        },
                    },
                    **payload,
                )
            ),
        )

    refusal_answer = "No binding support found."

    # ---- Route B: public law only — the Phase 1 engine, unchanged. ----
    if route == Route.VAULT_B:
        result = await answer_question(
            plan["rewritten_queries"]["b"],
            {},
            conn,
            tenant_id,
            user_ref,
            settings=settings,
            embedder=embedder,
            llm=llm,
            audit_extra={"route": route, "route_confidence": confidence},
        )
        result["route"] = Route.VAULT_B
        return result

    # ---- Routes A / BOTH ----
    # §2.2 matter binding: matter-scoped unless cross-matter clearance.
    matter_filter: dict[str, Any] = {}
    if matter_id and clearance not in _CROSS_MATTER:
        matter_filter = {"matter_id": str(matter_id)}

    if route == Route.VAULT_A:
        a_rows = await _retrieve(
            plan["rewritten_queries"]["a"],
            conn,
            tenant_id,
            settings,
            embedder,
            vault="firm",
            filters=matter_filter,
        )
        a_rows = await _decrypt_rows(a_rows or [], conn, provider)
        if not a_rows:
            await _audit({"threshold_passed": False, "answer_text": None, "citations": []})
            log.info("query_refused", reason="vault_a_miss", route=route)
            if mode == Mode.ADVISORY:
                return {
                    "answer": "Low confidence context—manual review recommended.",
                    "citations": [],
                    "refusal": False,
                    "advisory": True,
                    "route": Route.VAULT_A,
                }
            return {
                "answer": "No internal support found in Vault A.",
                "citations": [],
                "refusal": True,
                "route": Route.VAULT_A,
            }
        try:
            answer, citations = await _synthesize(
                question, a_rows=a_rows, b_rows=[], llm=llm, settings=settings
            )
        except CitationIntegrityError as exc:
            await _audit(
                {"threshold_passed": True, "answer_text": None, "citations": [],
                 "integrity_refusal": True}
            )
            log.warn("query_refused", reason="citation_integrity", detail=str(exc))
            return {"answer": refusal_answer, "citations": [], "refusal": True, "route": route}
        except TimeoutError:
            # answer_timeout_s ceiling, same contract as Phase 1: a timed-out
            # synthesis is a logged refusal, not a 500.
            await _audit({"threshold_passed": True, "answer_text": None, "citations": []})
            log.info("query_refused", reason="answer_timeout", route=route)
            return {"answer": refusal_answer, "citations": [], "refusal": True, "route": route}
        answer = _label_internal(answer)
        await _audit(
            {
                "threshold_passed": True,
                "answer_text": answer,
                "citations": citations,
                "retrieved_chunk_ids": [r["id"] for r in a_rows],
                "similarity_scores": [float(r["vsim"]) for r in a_rows if r["vsim"] is not None],
            }
        )
        return {"answer": answer, "citations": citations, "refusal": False, "route": route}

    # ---- BOTH: two retrieval legs. §2.2 shows asyncio.gather ("parallel
    # retrieval"); RECORDED ADAPTATION (rule 3): the Phase 1/2.3 stack runs
    # on one asyncpg connection per request, and asyncpg connections are
    # strictly sequential — two in-flight fetches on ctx.db raise
    # InterfaceError. The legs are therefore awaited in series on the same
    # RLS-scoped connection; the privilege contract is unchanged (both legs
    # execute under the caller's GUCs), only the latency overlap is lost.
    # A two-connection refactor belongs with the asyncpg->pool-per-leg work,
    # not silently here. ----
    a_leg = await _retrieve(
        plan["rewritten_queries"]["a"],
        conn,
        tenant_id,
        settings,
        embedder,
        vault="firm",
        filters=matter_filter,
    )
    b_leg = await _retrieve(
        plan["rewritten_queries"]["b"],
        conn,
        tenant_id,
        settings,
        embedder,
        vault="juris",
        filters={},
    )
    a_rows = await _decrypt_rows(a_leg or [], conn, provider)
    b_rows = b_leg or []

    if not a_rows and not b_rows:
        await _audit({"threshold_passed": False, "answer_text": None, "citations": []})
        log.info("query_refused", reason="dual_miss", route=route)
        if mode == Mode.ADVISORY:
            return {
                "answer": "Low confidence context—manual review recommended.",
                "citations": [],
                "refusal": False,
                "advisory": True,
                "route": Route.BOTH,
            }
        return {"answer": refusal_answer, "citations": [], "refusal": True, "route": Route.BOTH}

    internal_only = bool(a_rows) and not b_rows
    public_only = bool(b_rows) and not a_rows
    try:
        answer, citations = await _synthesize(
            question, a_rows=a_rows, b_rows=b_rows, llm=llm, settings=settings
        )
    except CitationIntegrityError as exc:
        await _audit(
            {"threshold_passed": True, "answer_text": None, "citations": [],
             "integrity_refusal": True}
        )
        log.warn("query_refused", reason="citation_integrity", detail=str(exc))
        return {"answer": refusal_answer, "citations": [], "refusal": True, "route": route}
    except TimeoutError:
        await _audit({"threshold_passed": True, "answer_text": None, "citations": []})
        log.info("query_refused", reason="answer_timeout", route=route)
        return {"answer": refusal_answer, "citations": [], "refusal": True, "route": route}
    if internal_only:
        answer = _label_internal(answer)
    elif public_only:
        answer = _label_public(answer)
    await _audit(
        {
            "threshold_passed": True,
            "answer_text": answer,
            "citations": citations,
            "retrieved_chunk_ids": [r["id"] for r in [*a_rows, *b_rows]],
            "similarity_scores": [
                float(r["vsim"]) for r in [*a_rows, *b_rows] if r["vsim"] is not None
            ],
        }
    )
    return {"answer": answer, "citations": citations, "refusal": False, "route": route}
