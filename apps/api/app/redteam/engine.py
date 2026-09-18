"""Legal Red-Teamer engine — Phase3-Design §2.1, adapted to Phase 1 reality.

Each adaptation is recorded (HANDOFF.md rule 3):
  * ``load_decrypted_text`` (Phase 2 envelope crypto) -> plain chunk load from
    ``document_chunks``; Step A analyzes ingested Vault B documents. Envelope
    decrypt swaps in when Phase 2 lands.
  * ``dual_vault_query`` (Phase 2 router) / ``rerank`` (Phase 3 4) -> the
    Phase 1 Vault B hybrid retrieval (RetrievalService), top rows per claim.
    The retrieval ORDER BY does not yet mirror the halfvec cast (Phase 3 4
    rerank replaces it anyway).
  * ``zdr_client.anthropic()`` -> the AnswerLLM protocol from
    app.retrieval.clients (same ZDR behavioural contract; injectable for
    tests).
  * Analysis is ADVISORY work-product: a below-gate claim retrieval yields an
    empty context for that claim rather than refusing the whole analysis;
    the matcher then drops anything that cannot be verified, and the critic
    decides pass/downgrade. Refusal contracts stay reserved for /v1/query
    and (later) Expert Chat.
  * §3.3 prompt packs (Step C): the chain is pack-parameterized via
    ``run_pack_analysis(pack, ...)``; ``run_redteam_analysis`` is the
    ADVERSAL_BRIEF registration, kept for existing callers/tests.

ZDR: no document text, prompt bodies, or card content in log lines — ids,
counts, and agent-stage names only.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import asyncpg
from pydantic import BaseModel

from app.config import Settings
from app.middleware.zdr import get_logger
from app.redteam.schemas import BattleCard, CriticVerdict
from app.retrieval.clients import AnswerLLM, Embedder, make_embedder, make_llm
from app.retrieval.service import RetrievalService

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids import cycle
    from app.redteam.packs import PromptPack

log = get_logger("redcase.redteam")

MODEL = "claude-3-5-sonnet-20241022"  # §2.1
MAX_REGENERATIONS = 1  # §2.1

# Agent system prompts — Phase3-Design §2.1 verbatim (contract text: rewording
# requires the Phase 3 seeded-brief tests to be re-run).
EXTRACTOR = """You are the RedCase Extractor. Analyze this opposing filing and
extract a claim graph. JSON only:
{"parties": {"claimant": "...", "defendant": "..."},
 "prayers": ["..."],
 "procedural_history": ["..."],
 "claims": [{"id": "c1", "type": "FACTUAL|LEGAL|PROCEDURAL",
             "text": "...", "cited_authorities": ["..."],
             "relief_sought": "..."}],
 "notable_dates": ["2024-03-12: hearing"], "document_type": "BRIEF|MOTION|AFFIDAVIT"}
Rules: extract ONLY what the document states. No inference."""

STRATEGIST = """You are a senior Nigerian litigation strategist (RedCase Strategist).
Given the opposing claim graph and retrieved context, produce a battle card.
For each procedural/jurisdictional flaw cite the specific rule/statute from context.
For each opposing argument: strength 1-10 (10 = near-fatal to us), our counter-argument,
and authority UUIDs drawn ONLY from <context_uuids>. Confidence = your certainty the
authority actually supports the counter. JSON per the battle-card schema."""

MATCHER = """You are the Citation Matcher. For each authority UUID cited in the
battle card, verify: (a) UUID exists in <context_uuids>, (b) the cited proposition
is actually supported by that passage's text. Output JSON:
{"valid": [{"uuid": "...", "supports": "..."}],
 "invalid": [{"uuid": "...", "reason": "..."}]}  — invalid citations are dropped."""

CRITIC = """You are the RedCase Legal Critic — an adversarial reviewer. Your job is
to KILL weak analysis before a partner sees it. Check:
1. Every counter-argument is logically responsive to the specific claim.
2. Every authority citation supports what it's cited for (cross-check passage text).
3. No argument relies on facts not in the claim graph or retrieved context.
4. Strength ratings are calibrated (7+ requires binding SC/CA authority).
Output JSON: {"pass": true|false, "section_feedback": {"procedural_flaws": "...",
"opposing_arguments": "..."}, "downgrade": ["section_ids"]}"""

_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def _extract_json(raw: str) -> dict[str, Any]:
    m = _JSON_BLOCK.search(raw)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))


async def run_agent(
    llm: AnswerLLM, system: str, payload: dict[str, Any], schema: type[BaseModel]
) -> BaseModel:
    """One agent stage: prompt -> LLM -> JSON -> validated schema.

    One parse/retry round with the validation error injected (the §2.1
    regeneration loop for the critic is separate and capped at
    MAX_REGENERATIONS)."""
    user = f"<payload>\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n</payload>"
    last_err: Exception | None = None
    for _attempt in range(2):
        try:
            raw = await llm.answer(system, user)
            return schema.model_validate(_extract_json(raw))
        except (ValueError, KeyError) as exc:  # JSON/validation failures
            last_err = exc
            user = (
                f"{user}\n<parse_error>Your previous output failed validation: "
                f"{exc}. Return ONLY the corrected JSON object.</parse_error>"
            )
    raise RuntimeError(f"agent stage failed after retry: {last_err}")


async def _load_document_text(db: asyncpg.Connection, document_id: str) -> str:
    rows = await db.fetch(
        "SELECT chunk_text FROM document_chunks"
        " WHERE document_id = $1::uuid ORDER BY chunk_index",
        document_id,
    )
    if not rows:
        raise RuntimeError(f"document {document_id} has no ingested chunks")
    return "\n\n".join(r["chunk_text"] for r in rows)


def drop_invalid_citations(
    card: BaseModel, match: dict[str, Any], match_sections: tuple[str, ...]
) -> int:
    """Matcher enforcement: citations not in ``invalid`` stay; invalid UUIDs
    are removed from every authority list. Items left with no authority go to
    manual review (they could not be verified). Pack-agnostic: the caller
    names the ``sections`` attributes whose items carry ``authority``."""
    invalid = set()
    for m in match.get("invalid", []):
        if "uuid" not in m:
            continue
        u = m["uuid"]
        # The matcher's echo format is not contractual (a production LLM may
        # return the bare uuid or the B:-prefixed citation form), so compare
        # against both representations.
        invalid.add(u)
        invalid.add(u[2:] if u.startswith("B:") else f"B:{u}")
    dropped = 0
    sections = card.sections
    for section_name in match_sections:
        for item in getattr(sections, section_name):
            if not hasattr(item, "authority"):
                continue
            kept = [a for a in item.authority if a not in invalid]
            dropped += len(item.authority) - len(kept)
            item.authority = kept
            if not kept and hasattr(item, "manual_review"):
                item.manual_review = True
    return dropped


def downgrade_sections(card: BaseModel, downgrade: list[str]) -> None:
    """Critic downgrade: mark affected items for manual review so the UI can
    badge them [MANUAL REVIEW] (Phase3 §2.2). HIGH->LOW remap applies only to
    battle-card flaws (severity field); other packs get manual_review only."""
    if "procedural_flaws" in downgrade:
        for f in card.sections.procedural_flaws:  # type: ignore[attr-defined]
            f.severity = "LOW"
    for name in downgrade:
        for item in getattr(card.sections, name, []):
            if hasattr(item, "manual_review"):
                item.manual_review = True


async def run_pack_analysis(
    pack: PromptPack,
    document_id: str,
    tenant_id: str,
    db: asyncpg.Connection,
    *,
    settings: Settings,
    llm: AnswerLLM | None = None,
    embedder: Embedder | None = None,
) -> BaseModel:
    """The §2.1 chain, pack-parameterized (§3.3, Step C): pack Extractor ->
    per-claim Vault B retrieval -> pack Specialist -> Matcher -> Critic
    (one regeneration cap). Returns a schema-valid pack output (BattleCard
    for ADVERSAL_BRIEF, SummonsResponseOutput / ContractReviewOutput for
    the §3.3 packs); authority UUIDs are matcher-verified against retrieved
    context."""
    llm = llm or make_llm(settings)
    embedder = embedder or make_embedder(settings)
    log.info("pack_analysis_start", pack=pack.name, document_id=document_id)

    text = await _load_document_text(db, document_id)
    graph: BaseModel = await run_agent(  # type: ignore[assignment]
        llm, pack.extractor_prompt, {"document_text": text}, pack.extractor_schema
    )
    # Every pack extractor exposes its claim-shaped items under a section
    # list: `claims` (ADVERSAL_BRIEF, SUMMONS_RESPONSE) or `clauses`
    # (CONTRACT_REVIEW).
    claims = getattr(graph, "claims", None) or graph.clauses
    log.info(
        "pack_extracted", pack=pack.name, document_id=document_id, claims=len(claims)
    )

    # Per-claim retrieval (§2.1): LEGAL claims each get a query; PROCEDURAL
    # claims share one combined query.
    svc = RetrievalService(db, tenant_id)
    legal = [c for c in claims if c.type == "LEGAL"]
    proc = [c for c in claims if c.type == "PROCEDURAL"]
    queries = [c.text for c in legal]
    keys: list[Any] = [*legal]
    if proc:
        queries.append(" ".join(c.text for c in proc))
        keys.append(None)

    contexts: dict[str, list[dict[str, Any]]] = {}
    uuids: set[str] = set()
    for key, q in zip(keys, queries, strict=True):
        qvec = (await embedder.embed([q]))[0]
        rows = await svc.retrieve(q, qvec, {})
        label = key.id if key else "_proc"
        # asyncpg rows carry UUID/datetime values — normalize to JSON-safe
        # dicts before they go into any prompt payload.
        contexts[label] = json.loads(json.dumps(rows or [], default=str))
        for r in rows or []:
            uuids.add(f"B:{r['document_id']}")

    output: BaseModel | None = None
    critic_feedback = ""
    for attempt in range(MAX_REGENERATIONS + 1):
        specialist = pack.specialist_prompt + (
            f"\n<critic_feedback>{critic_feedback}</critic_feedback>"
            if critic_feedback
            else ""
        )
        output = await run_agent(  # type: ignore[assignment]
            llm,
            specialist,
            {
                "extracted": graph.model_dump(),
                "contexts": contexts,
                "context_uuids": sorted(uuids),
            },
            pack.output_schema,
        )
        output.source_document_id = document_id
        output.generated_at = datetime.now(UTC).isoformat()

        output_json = output.model_dump(by_alias=True, mode="json")
        match_payload = json.dumps(
            {
                "output": output_json,
                "context_uuids": sorted(uuids),
                "passages": contexts,
            },
            ensure_ascii=False,
        )
        raw_match = await llm.answer(
            MATCHER, f"<payload>\n{match_payload}\n</payload>"
        )
        dropped = drop_invalid_citations(
            output, _extract_json(raw_match), pack.match_sections
        )
        log.info("pack_matched", pack=pack.name, document_id=document_id, dropped=dropped)

        verdict_payload = json.dumps(
            {
                "output": output_json,
                "extracted": graph.model_dump(),
                "passages": contexts,
            },
            ensure_ascii=False,
        )
        raw_verdict = await llm.answer(
            CRITIC, f"<payload>\n{verdict_payload}\n</payload>"
        )
        critic_json = _extract_json(raw_verdict)
        # §2.1 critic keys: "pass", "section_feedback", "downgrade" — mapped
        # onto the §1.2 verdict shape (downgraded_sections).
        passed = bool(critic_json.get("pass"))
        downgrade = list(critic_json.get("downgrade") or [])
        log.info(
            "pack_critic",
            pack=pack.name,
            document_id=document_id,
            attempt=attempt,
            passed=passed,
            downgrade=downgrade,
        )
        if passed:
            output.critic_verdict = CriticVerdict(
                **{"pass": True, "regenerations": attempt, "downgraded_sections": []}
            )
            break
        if attempt == MAX_REGENERATIONS:
            downgrade_sections(output, downgrade)
            output.critic_verdict = CriticVerdict(
                **{
                    "pass": False,
                    "regenerations": attempt,
                    "downgraded_sections": downgrade,
                }
            )
        else:
            critic_feedback = json.dumps(critic_json.get("section_feedback") or {})

    if output is None:  # pragma: no cover — loop always assigns; guard for mypy
        raise RuntimeError("pack loop produced no output")
    log.info(
        "pack_complete",
        pack=pack.name,
        document_id=document_id,
        passed=output.critic_verdict.pass_,
        regenerations=output.critic_verdict.regenerations,
    )
    return output


async def run_redteam_analysis(
    document_id: str,
    tenant_id: str,
    db: asyncpg.Connection,
    *,
    settings: Settings,
    llm: AnswerLLM | None = None,
    embedder: Embedder | None = None,
) -> BattleCard:
    """ADVERSAL_BRIEF registration of the §2.1 chain — kept verbatim for
    existing callers (Step A worker contract, seeded-brief tests)."""
    from app.redteam.packs import PACKS

    card = await run_pack_analysis(
        PACKS["ADVERSAL_BRIEF"],
        document_id,
        tenant_id,
        db,
        settings=settings,
        llm=llm,
        embedder=embedder,
    )
    return card  # type: ignore[no-any-return]
