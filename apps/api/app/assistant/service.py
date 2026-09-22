"""Legal Assistant — the ONE conversational agent (Addendum §7.2).

A bounded ReAct agent (planner -> executor -> verifier, max 6 tool iterations)
that dialogues ONLY within the caller's own Workbench. Tools wrap existing
contracts and respect the caller's grants via RLS (the request connection's
app.tenant_id / app.user_ref / app.user_clearance GUCs are enforced in SQL).

Grounding contract: every legal proposition must carry a verified namespace
citation ([A:...] firm docs, [B:...] jurisprudence) checked by
verify_namespaced_citations; a fabricated citation is a hard refusal (the
fabricated text is never shown or persisted). Strategic commentary is labeled.
Serving provider is recorded per turn.

ZDR: no document text / prompt bodies / LLM payloads in any persist or log —
user text + assistant reply are the system of record (assistant_messages);
retrieved text and tool payloads live only in memory.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from types import SimpleNamespace as _SimpleNamespace
from typing import Any

import asyncpg

from app.config import Settings
from app.middleware.zdr import get_logger
from app.retrieval.clients import AnswerLLM, make_llm
from app.retrieval.service import RetrievalService
from app.router.service import extract_json, verify_namespaced_citations

log = get_logger("redcase.assistant")

MAX_TOOL_ITERATIONS = 6  # Addendum §7.2 hard bound on the ReAct loop
ALLOWED_TOOLS = {
    "search_vault_a",
    "search_vault_b",
    "analyze_document",
    "matter_context",
    "save_to_workbench",
}
_CROSS_MATTER = ("PARTNER", "ADMIN")

AGENT_SYSTEM = """You are the RedCase Legal Assistant — a per-user, grounded legal
research and drafting assistant for one licensed lawyer. You work ONLY from the tool
results provided to you; you never rely on training knowledge of Nigerian law, and you
never invent a case, citation, page, or justice.

You take actions one at a time. Each turn reply with JSON only, one of:

1. To run a tool:
   {{{{"action": "search_vault_a", "action_input": {{{{"query": "...", "matter_id": "..."|null}}}}}}
   {{{{"action": "search_vault_b", "action_input": {{{{"query": "..."}}}}}}
   {{{{"action": "analyze_document", "action_input": {{{{"
        "document_id": "...", "prompt_pack": "..."}}}}}}
   {{{{"action": "matter_context", "action_input": {{{{}}}}}}
   {{{{"action": "save_to_workbench", "action_input": {{{{"title": "."
        "..", "body": "...", "kind": "DRAFT"|"NOTE"}}}}}}

2. To answer the user:
   {{{{"final": {{{{"answer": "...", "refusal_block": null|"."
        ".."}}}}}}
   - Every legal proposition must be followed by a namespace-tagged citation
     [A:doc_id, p.X] or [B:doc_id, citation, p.X] whose doc_id appears in
     the tool results you have seen. Cite ONLY ids you actually saw.
   - If NO tool result supports the proposition, output a refusal: set
     "refusal_block" and give the supported part only.
   - Strategic/drafting content must be labeled as internal strategy, never as law.

You have at most {max_iterations} tool uses. Stop with {{{{"final": ...}}}} when you have
enough verified grounding to answer.

User preferences pasted below (follow them when drafting):
{preferences}
"""


@dataclass
class ToolResult:
    tool: str
    ok: bool
    summary: str
    rows: list[dict[str, Any]] = field(default_factory=list)
    namespace: str | None = None  # "A" or "B" when it returns retrievable docs


@dataclass
class AssistantReply:
    content: str
    citations: list[dict[str, Any]]
    refusal: bool
    tool_uses: list[dict[str, Any]]
    serving_provider: str | None = None
    serving_model: str | None = None


async def _fetch_preferences(
    db: asyncpg.Connection, tenant_id: str, user_ref: str
) -> list[dict[str, Any]]:
    rows = await db.fetch(
        "SELECT pref_key, pref_value, source FROM assistant_preferences"
        " WHERE tenant_id = $1::uuid AND user_ref = $2 ORDER BY created_at",
        uuid.UUID(tenant_id),
        user_ref,
    )
    return [
        {"key": r["pref_key"], "value": r["pref_value"], "source": r["source"]}
        for r in rows
    ]


def _preference_block(prefs: list[dict[str, Any]]) -> str:
    if not prefs:
        return "(none yet)"
    lines = [
        f"- {p['key']}: {json.dumps(p['value'], ensure_ascii=False)}"
        f" (from {p['source'].lower()})"
        for p in prefs
    ]
    return "\n".join(lines)


# --- Internal tools (each wraps an existing contract) ---------------------------

async def _search_vault_a(
    db: asyncpg.Connection,
    tenant_id: str,
    user_ref: str,
    clearance: str,
    settings: Settings,
    embedder: Any,
    query: str,
    matter_id: str | None,
) -> ToolResult:
    """Firm-document retrieval, grant-scoped by RLS and the §2.2 matter-binding
    ruling (non-cross-matter users are confined to the supplied matter)."""
    filters: dict[str, Any] = {}
    if matter_id:
        filters["matter_id"] = matter_id
    svc = RetrievalService(db, tenant_id)
    qvec = (await embedder.embed([query]))[0]
    rows = await svc.retrieve(
        query,
        qvec,
        filters,
        threshold=settings.vector_gate,
        top_k=settings.retrieval_top_k,
        per_doc_cap=settings.retrieval_per_doc_cap,
        ratio_exempt=settings.retrieval_ratio_exempt,
        vault="firm",
    )
    if not rows:
        return ToolResult(
            tool="search_vault_a",
            ok=False,
            summary="No firm documents matched (below similarity gate or out of scope).",
            namespace="A",
        )
    body = "\n\n".join(
        f'<passage ns="A" doc_id="{r["document_id"]}" pages="{r["page_start"]}-{r["page_end"]}">'
        f'\n{r["chunk_text"]}\n</passage>'
        for r in rows
    )
    return ToolResult(
        tool="search_vault_a",
        ok=True,
        summary=f"{len(rows)} firm passage(s) retrieved (namespace A).\n{body}",
        rows=rows,
        namespace="A",
    )


async def _search_vault_b(
    db: asyncpg.Connection,
    tenant_id: str,
    user_ref: str,
    settings: Settings,
    query: str,
    llm: AnswerLLM,
    embedder: Any,
    thread_id: str,
) -> ToolResult:
    """Jurisprudence via the grounded answer_question engine (audits its own row)."""
    from app.retrieval.service import answer_question

    result = await answer_question(
        query,
        {},
        db,
        tenant_id,
        user_ref,
        settings=settings,
        embedder=embedder,
        llm=llm,
        thread_id=thread_id,
    )
    if result.get("refusal"):
        return ToolResult(
            tool="search_vault_b",
            ok=False,
            summary=result.get("answer", ""),
            rows=[],
            namespace="B",
        )
    return ToolResult(
        tool="search_vault_b",
        ok=True,
        summary=result.get("answer", ""),
        rows=result.get("citations", []),
        namespace="B",
    )


async def _matter_context(
    db: asyncpg.Connection, tenant_id: str, user_ref: str
) -> ToolResult:
    """Per-user matter + time summary (ZDR: ids and counts only)."""
    rows = await db.fetch(
        "SELECT m.id, m.matter_ref, m.status, c.name AS client_name,"
        " (SELECT COUNT(*) FROM time_entries t WHERE t.matter_id = m.id"
        "  AND t.user_ref = $2) AS my_entries"
        " FROM matters m"
        " JOIN clients c ON c.id = m.client_id"
        " WHERE m.tenant_id = $1::uuid"
        " ORDER BY m.opened_at DESC LIMIT 20",
        uuid.UUID(tenant_id),
        user_ref,
    )
    if not rows:
        return ToolResult(
            tool="matter_context", ok=True, summary="No matters for your firm yet.", rows=[]
        )
    summary = "\n".join(
        f"- {r['matter_ref']} ({r['client_name']}, {r['status']}, "
        f"my_entries={r['my_entries']})"
        for r in rows
    )
    return ToolResult(
        tool="matter_context",
        ok=True,
        summary=f"{len(rows)} matter(s):\n{summary}",
        rows=[dict(r) for r in rows],
    )


async def _save_to_workbench(
    db: asyncpg.Connection,
    tenant_id: str,
    user_ref: str,
    thread_id: str,
    title: str,
    body: str,
    kind: str,
) -> ToolResult:
    kind = "NOTE" if kind not in ("DRAFT", "NOTE") else kind
    artifact_id = uuid.uuid4()
    await db.execute(
        "INSERT INTO assistant_artifacts (id, tenant_id, thread_id, created_by, kind, title, body)"
        " VALUES ($1, $2, $3, $4, $5, $6, $7)",
        artifact_id,
        uuid.UUID(tenant_id),
        uuid.UUID(thread_id),
        user_ref,
        kind,
        title[:300],
        body,
    )
    return ToolResult(
        tool="save_to_workbench",
        ok=True,
        summary=f"Saved {kind} '{title}' to your workbench (artifact {artifact_id}).",
        rows=[{"artifact_id": str(artifact_id), "kind": kind}],
    )



async def _load_history(
    db: asyncpg.Connection, thread_id: str
) -> list[dict[str, Any]]:
    rows = await db.fetch(
        "SELECT role, content FROM assistant_messages WHERE thread_id = $1::uuid"
        " ORDER BY created_at LIMIT 50",
        uuid.UUID(thread_id),
    )
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def _first_line(text: str, n: int) -> str:
    line = text.strip().splitlines()[0] if text.strip() else "Untitled thread"
    return (line[:n] + "…") if len(line) > n else (line or "Untitled thread")


def _build_agent_prompt(
    message_text: str,
    history: list[dict[str, Any]],
    tool_desc: str,
    ctx: Any,
    settings: Settings,
) -> str:
    """Assemble the executor prompt FROM MEMORY-ONLY state (history, tool results).
    Retrieved chunk text is passed in-memory to the LLM but never persisted/logged
    (ZDR)."""
    conv = "\n".join(f"{h['role']}: {h['content']}" for h in history)
    lines = [
        "<user_message>",
        message_text,
        "</user_message>",
        "<conversation_history>",
        conv if conv else "(new thread)",
        "</conversation_history>",
        "<tool_observations>",
        tool_desc if tool_desc else "(no tool calls yet)",
        "</tool_observations>",
        "<retrieved_grounding>",
        ctx.b_answer if ctx.b_answer else "(no grounded authority retrieved yet)",
        "</retrieved_grounding>",
        "Now reply with your next JSON action, or a {final: ...} answer.",
    ]
    return "\n".join(lines)


def _parse_decision(raw: str) -> dict[str, Any] | None:
    """Isolate ONE JSON object (action or final) from the agent's output."""
    try:
        return json.loads(extract_json(raw))
    except (json.JSONDecodeError, ValueError):
        return None


async def run_assistant_turn(
    *,
    thread_id: str,
    message_text: str,
    db: asyncpg.Connection,
    tenant_id: str,
    user_ref: str,
    clearance: str,
    settings: Settings,
    llm: AnswerLLM | None = None,
    embedder: Any | None = None,
    save_history: bool = True,
) -> AssistantReply:
    """One user turn through the bounded ReAct loop (planner -> executor ->
    verifier). llm/embedder are injectable for tests; production resolves from
    settings. ``save_history`` lets callers that only need a dry grounding run
    (verify/feedback round-trip tests) skip persistence."""
    from app.retrieval.clients import make_embedder

    llm = llm or make_llm(settings)
    embedder = embedder or make_embedder(settings)

    prefs = await _fetch_preferences(db, tenant_id, user_ref)
    system = AGENT_SYSTEM.format(
        max_iterations=MAX_TOOL_ITERATIONS,
        preferences=_preference_block(prefs),
    )
    history = await _load_history(db, thread_id)

    # Per-turn accumulation namespaces for the verifier hard gate.
    a_rows: list[dict[str, Any]] = []
    b_rows: list[dict[str, Any]] = []
    b_answer: str | None = None
    tool_uses: list[dict[str, Any]] = []


    async def _run_tool(tool: str, inp: dict[str, Any]) -> ToolResult:
        nonlocal a_rows, b_rows, b_answer
        if tool == "search_vault_a":
            res = await _search_vault_a(
                db, tenant_id, user_ref, clearance, settings, embedder,
                str(inp.get("query", "")), inp.get("matter_id"),
            )
        elif tool == "search_vault_b":
            res = await _search_vault_b(
                db, tenant_id, user_ref, settings, str(inp.get("query", "")),
                llm, embedder, thread_id,
            )
            if res.namespace == "B":
                b_answer = res.summary
        elif tool == "matter_context":
            res = await _matter_context(db, tenant_id, user_ref)
        elif tool == "save_to_workbench":
            res = await _save_to_workbench(
                db, tenant_id, user_ref, thread_id,
                str(inp.get("title", "Untitled")), str(inp.get("body", "")),
                str(inp.get("kind", "NOTE")),
            )
        elif tool == "analyze_document":
            res = ToolResult(
                tool=tool,
                ok=False,
                summary=(
                    "analyze_document is a pipeline-owned worker; it is not "
                    "available in async conversation. Suggest /v1/documents/{id}/analyze."
                ),
            )
        else:
            res = ToolResult(tool=tool, ok=False, summary="unknown tool")
        if res.namespace == "A" and res.rows:
            a_rows.extend(res.rows)
        if res.namespace == "B" and res.rows:
            b_rows.extend(res.rows)
        return res

    # The executor loop — a ToolResult's summary (which may embed retrieved passage
    # text in memory) is passed to the LLM but never persisted (ZDR).
    final_content: str | None = None
    refusal_block: str | None = None
    for iteration in range(1, MAX_TOOL_ITERATIONS + 1):
        ctx = _SimpleNamespace(b_answer=b_answer)
        tool_desc = "\n".join(
            f"[{t.get('tool')}] {t.get('summary', '')}" for t in tool_uses
        )
        prompt = _build_agent_prompt(message_text, history, tool_desc, ctx, settings)
        raw = await llm.answer(system, prompt)
        decision = _parse_decision(raw)
        if decision is None:
            refusal_block = "The assistant could not form a valid action. Please rephrase."
            break
        if "final" in decision:
            final_content = str(decision["final"].get("answer", ""))
            refusal_block = decision["final"].get("refusal_block")
            break
        action = decision.get("action")
        inp = decision.get("action_input") or {}
        if action not in ALLOWED_TOOLS:
            tool_uses.append(
                {
                    "tool": str(action or "?"),
                    "query_hash": None,
                    "iterations": iteration,
                    "ok": False,
                }
            )
            refusal_block = "I can only use my internal research tools. Please rephrase."
            break
        res = await _run_tool(action, inp)
        query_text = inp.get("query")
        tool_uses.append(
            {
                "tool": action,
                "query_hash": (
                    hashlib.sha256(str(query_text).encode()).hexdigest()
                    if query_text
                    else None
                ),
                "iterations": iteration,
                "ok": res.ok,
            }
        )


    # --- Verifier stage: zero-fabrication hard gate ---
    if final_content is None:
        content = refusal_block or "I was unable to complete that request."
        refusal = True
        citations: list[dict[str, Any]] = []
    else:
        try:
            citations = verify_namespaced_citations(final_content, a_rows, b_rows)
        except Exception as exc:  # CitationIntegrityError
            log.warn(
                "assistant_citation_integrity",
                thread_id=thread_id,
                reason=str(exc)[:200],
            )
            content = (
                "I cannot show that answer: it cited material outside what my grounded "
                "research returned. I'll only answer from verified sources."
            )
            refusal = True
            citations = []
        else:
            refusal = refusal_block is not None
            content = final_content

    if not save_history:
        return AssistantReply(
            content=content,
            citations=citations,
            refusal=refusal,
            tool_uses=tool_uses,
            serving_provider=getattr(llm, "provider", None),
            serving_model=getattr(llm, "model", None),
        )

    # --- Persistent system of record (user text + assistant reply) ---
    await db.execute(
        "INSERT INTO assistant_messages (id, tenant_id, thread_id, role, content, question_hash)"
        " VALUES ($1, $2, $3, 'USER', $4, $5)",
        uuid.uuid4(),
        uuid.UUID(tenant_id),
        uuid.UUID(thread_id),
        message_text,
        hashlib.sha256(message_text.encode()).hexdigest(),
    )
    await db.execute(
        "INSERT INTO assistant_messages (id, tenant_id, thread_id, role, content,"
        " citations, tool_uses, serving_provider, serving_model)"
        " VALUES ($1, $2, $3, 'ASSISTANT', $4, $5::jsonb, $6::jsonb, $7, $8)",
        uuid.uuid4(),
        uuid.UUID(tenant_id),
        uuid.UUID(thread_id),
        content,
        json.dumps(citations or []),
        json.dumps(tool_uses or []),
        getattr(llm, "provider", None),
        getattr(llm, "model", None),
    )
    await db.execute(
        "UPDATE assistant_threads SET title = $2, updated_at = now() WHERE id = $1",
        uuid.UUID(thread_id),
        _first_line(message_text, 80),
    )
    log.info(
        "assistant_turn",
        thread_id=thread_id,
        iterations=len(tool_uses),
        refusal=refusal,
        citations=len(citations),
    )
    return AssistantReply(
        content=content,
        citations=citations,
        refusal=refusal,
        tool_uses=tool_uses,
        serving_provider=getattr(llm, "provider", None),
        serving_model=getattr(llm, "model", None),
    )


