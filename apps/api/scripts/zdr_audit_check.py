"""ZDR verification script (Task 1.7 DoD item, HANDOFF.md 2.1).

Asserts the zero-data-retention bar against the LIVE database and local log
sinks:

  1. query_audit carries the question only as SHA-256 (no question-text or
     prompt-body column exists in the schema).
  2. No prompt body is persisted anywhere: the GROUNDED_SYSTEM/GROUNDED_USER
     marker strings must not appear in any non-corpus table.
  3. No raw corpus text in any persisted store outside the corpus tables
     themselves: sampled RECENT rows (--since-days, default 2 — the audit
     trail is immutable and pre-amendment history is out of scope) of every
     non-corpus table are scanned for verbatim 8-gram overlap with sampled
     document_chunks.chunk_text. query_audit.answer_text is generated
     output (auditable per the Phase1 DDL comment): incidental holding
     quotes are legitimate there, so it gets a longer 12-gram window with
     a 3-hit threshold; pasted-passage leakage still flags.
     (Corpus tables — document_chunks, documents — ARE the vault by design;
     excluding them is the check's scope, recorded here.)
  4. No ZDR-protected content in local log sinks: recent *.log / *.jsonl
     files under the app directory are scanned for corpus 8-grams, prompt
     markers, and unredacted banned keys (ZDRFilter's key set).
  5. Secret patterns (API-key shapes) appear in no sampled store or log.

Findings never print the leaked content itself — only location and kind
(ZDR discipline applies to this script's own output).

Exit code 0 = clean; 1 = at least one finding. Read-only throughout.

Usage (from apps/api, with .env loaded):
  python -m scripts.zdr_audit_check
  python -m scripts.zdr_audit_check --sample-chunks 300 --sample-rows 200
"""

import argparse
import asyncio
import json
import re
import uuid
from pathlib import Path

import asyncpg

from app.config import get_settings
from app.middleware.zdr import DEFAULT_REDACT_KEYS

# Corpus tables: raw document text is their DESIGN payload (the vault).
# Everything else must be free of verbatim corpus overlap.
CORPUS_TABLES = {"document_chunks", "documents"}

# The grounding prompt contract: if these strings sit in a persisted store,
# a prompt body leaked. The refusal sentence is deliberately NOT here — it
# is both rule-3 output and the API response contract, so its presence is
# not evidence of a prompt-body leak.
PROMPT_MARKERS = (
    "You are the RedCase Vault B research engine",
    "<passages>",
    "<question>",
)

# API-key shapes — ZDR-adjacent: secrets never land in stores or logs.
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b"),
)

NGRAM = 8  # word-level verbatim overlap window for stores that must be clean
# query_audit.answer_text is GENERATED OUTPUT (auditable per the Phase1 DDL
# comment), so an incidental holding quote is legitimate. Pasted-passage
# leakage there is caught with a longer window + a multi-hit threshold.
ANSWER_NGRAM = 12
ANSWER_HIT_THRESHOLD = 3
# Nigerian Supreme Court judgments share long formulaic phrases ("It is
# hereby ordered that the judgment of the Court of Appeal..."). A 12-gram
# appearing in >=3 corpus chunks is boilerplate, not leakage.
BOILERPLATE_FREQ = 3

TEXTUAL_TYPES = {"text", "character varying", "character"}


def _ngrams(text: str, n: int = NGRAM) -> set[str]:
    words = text.lower().split()
    if len(words) < n:
        return set()
    return {" ".join(words[i : i + n]) for i in range(len(words) - n + 1)}


async def _column_sample(
    conn: asyncpg.Connection, table: str, column: str, limit: int, since_days: int
) -> list[str]:
    """Sample non-null values, restricted to recent rows when the table
    carries created_at. Verification asserts CURRENT config behaviour;
    pre-amendment history in the immutable audit trail is out of scope."""
    has_ts = await conn.fetchval(
        "SELECT count(*) FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = $1"
        " AND column_name = 'created_at'",
        table,
    )
    where = f'"{column}" IS NOT NULL'
    order = ""
    if has_ts:
        where += f" AND created_at > now() - interval '{float(since_days)} days'"
        order = " ORDER BY created_at DESC"
    rows = await conn.fetch(
        # identifiers originate from information_schema, not user input
        f'SELECT "{column}" FROM "{table}" WHERE {where}{order}'  # noqa: S608
        f" LIMIT $1",
        limit,
    )
    return [r[column] for r in rows if isinstance(r[column], str) and r[column]]


async def _scan_table(
    dsn: str,
    table: str,
    columns: list,
    corpus_ngrams: set[str],
    sample_rows: int,
    since_days: int,
    findings: list[str],
    checked: list[str],
) -> None:
    """Scan one table's textual columns on a DEDICATED connection (the live
    Supabase link drops long scans; a per-table connection with one retry
    keeps the run robust). A table that fails twice is a finding, not a
    skip — an unscanned table cannot evidence ZDR compliance."""
    for attempt in (1, 2):
        try:
            conn = await asyncpg.connect(dsn, statement_cache_size=0)
            try:
                for c in columns:
                    col = c["column_name"]
                    samples = await _column_sample(conn, table, col, sample_rows, since_days)
                    if not samples:
                        continue
                    checked.append(f"{table}.{col}: {len(samples)} rows sampled")
                    for marker in PROMPT_MARKERS:
                        if any(marker in s for s in samples):
                            findings.append(f"PROMPT BODY in {table}.{col} (marker present)")
                            break
                    # query_audit.answer_text is generated output and is
                    # owned by _scan_answer_text (cited/retrieved exclusion).
                    if table == "query_audit" and col == "answer_text":
                        continue
                    for s in samples:
                        hits = _ngrams(s) & corpus_ngrams
                        if hits:
                            findings.append(
                                f"CORPUS TEXT in {table}.{col} ({len(hits)} 8-gram overlap)"
                            )
                            break
                    for s in samples:
                        if any(p.search(s) for p in SECRET_PATTERNS):
                            findings.append(f"SECRET PATTERN in {table}.{col}")
                            break
            finally:
                await conn.close()
            return
        except (asyncpg.ConnectionDoesNotExistError, asyncpg.ConnectionFailureError):
            if attempt == 2:
                findings.append(f"TABLE SCAN FAILED {table} (connection lost twice)")


async def _scan_answer_text(
    dsn: str,
    chunk_rows: list,
    sample_rows: int,
    since_days: float,
    findings: list[str],
    checked: list[str],
) -> None:
    """query_audit.answer_text is GENERATED OUTPUT (auditable per the Phase1
    DDL comment), and a grounded legal answer legitimately quotes passages it
    was shown. The ZDR bar is therefore precise: an answer must contain no
    verbatim corpus text BEYOND what it cited or was retrieved, beyond
    formulaic boilerplate shared across the corpus. Overlaps with cited
    documents' or retrieved chunks' text are grounded quotation; overlaps
    with anything else are flagged (12-gram, >=3 hits)."""
    from collections import Counter

    chunk_ngrams = {r["id"]: _ngrams(r["chunk_text"], ANSWER_NGRAM) for r in chunk_rows}
    chunk_doc = {r["id"]: r["document_id"] for r in chunk_rows}
    freq: Counter = Counter()
    for ng in chunk_ngrams.values():
        for g in ng:
            freq[g] += 1
    for attempt in (1, 2):
        try:
            conn = await asyncpg.connect(dsn, statement_cache_size=0)
            try:
                rows = await conn.fetch(
                    "SELECT id, answer_text, citations, retrieved_chunk_ids"  # noqa: S608
                    " FROM query_audit WHERE answer_text IS NOT NULL"
                    f" AND created_at > now() - interval '{since_days} days'"
                    " ORDER BY created_at DESC LIMIT $1",
                    sample_rows,
                )
                checked.append(
                    f"query_audit.answer_text: {len(rows)} rows (cited/retrieved-excluded scan)"
                )
                for r in rows:
                    ans = r["answer_text"]
                    for marker in PROMPT_MARKERS:
                        if marker in ans:
                            findings.append("PROMPT BODY in query_audit.answer_text")
                            break
                    raw = r["citations"]
                    try:
                        cites = json.loads(raw) if isinstance(raw, str) else (raw or [])
                    except json.JSONDecodeError:
                        cites = []
                    cited_docs = set()
                    for c in cites:
                        if isinstance(c, dict) and c.get("document_id"):
                            try:
                                cited_docs.add(uuid.UUID(str(c["document_id"])))
                            except (ValueError, AttributeError, KeyError):
                                pass
                    retrieved = set(r["retrieved_chunk_ids"] or [])
                    forbidden = {
                        g
                        for cid, ng in chunk_ngrams.items()
                        if cid not in retrieved and chunk_doc.get(cid) not in cited_docs
                        for g in ng
                        if freq[g] < BOILERPLATE_FREQ
                    }
                    hits = _ngrams(ans, ANSWER_NGRAM) & forbidden
                    if len(hits) >= ANSWER_HIT_THRESHOLD:
                        findings.append(
                            "CORPUS TEXT in query_audit.answer_text"
                            f" ({len(hits)} 12-grams beyond cited/retrieved/boilerplate)"
                        )
            finally:
                await conn.close()
            return
        except (asyncpg.ConnectionDoesNotExistError, asyncpg.ConnectionFailureError):
            if attempt == 2:
                findings.append("ANSWER SCAN FAILED (connection lost twice)")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-chunks", type=int, default=300)
    ap.add_argument("--sample-rows", type=int, default=200)
    ap.add_argument(
        "--since-days",
        type=float,
        default=2,
        help="Only rows newer than this are verified (audit history is immutable).",
    )
    ap.add_argument(
        "--log-glob",
        action="append",
        default=["logs/**/*.log", "logs/**/*.jsonl", "*.log", "*.jsonl"],
        help="Log-sink globs relative to the app directory (repeatable).",
    )
    args = ap.parse_args()

    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL not set — cannot verify persisted stores.")

    findings: list[str] = []
    checked: list[str] = []

    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)
    try:
        # -- 1. query_audit schema: hash-only question ----------------------
        cols = await conn.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_name = 'query_audit'"
        )
        names = {c["column_name"].lower() for c in cols}
        banned = names & {"question", "question_text", "question_body", "prompt", "prompt_body"}
        if banned:
            findings.append(f"query_audit schema: banned column(s) present: {sorted(banned)}")
        checked.append(f"query_audit schema ({len(names)} columns, hash-only question)")

        # -- 2/3. prompt markers + corpus 8-grams in non-corpus tables ------
        chunks = await conn.fetch(
            "SELECT id, document_id, chunk_text FROM document_chunks"
            " WHERE chunk_text IS NOT NULL ORDER BY id LIMIT $1",
            args.sample_chunks,
        )
        corpus_ngrams: set[str] = set()
        for r in chunks:
            corpus_ngrams |= _ngrams(r["chunk_text"])
        if not corpus_ngrams:
            raise SystemExit("No corpus sample built — document_chunks empty? Refusing to pass.")
        checked.append(
            f"corpus fingerprint: {len(corpus_ngrams)} 8-grams from {len(chunks)} chunks"
        )

        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        )
        for t in tables:
            table = t["table_name"]
            if table in CORPUS_TABLES:
                continue
            columns = await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns"
                " WHERE table_name = $1 AND data_type = ANY($2::text[])",
                table,
                list(TEXTUAL_TYPES),
            )
            if not columns:
                continue
            await _scan_table(
                settings.database_url, table, columns, corpus_ngrams,
                args.sample_rows, args.since_days, findings, checked,
            )

        # answer_text: generated output, cited/retrieved-excluded precision
        await _scan_answer_text(
            settings.database_url, list(chunks),
            args.sample_rows, args.since_days, findings, checked,
        )

        # -- 4/5. local log sinks -------------------------------------------
        app_dir = Path(__file__).resolve().parent.parent  # noqa: ASYNC240 (script)
        log_files: list[Path] = []
        for glob in args.log_glob:
            log_files.extend(app_dir.glob(glob))
        for lf in sorted(set(log_files)):
            try:
                text = lf.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:  # pragma: no cover - defensive
                findings.append(f"LOG UNREADABLE {lf.name}: {exc}")
                continue
            checked.append(f"log sink {lf.name}: {len(text)} chars")
            for marker in PROMPT_MARKERS:  # refusal sentence is legit log/response text
                if marker in text:
                    findings.append(f"PROMPT BODY in log {lf.name}")
                    break
            if _ngrams(text) & corpus_ngrams:
                findings.append(f"CORPUS TEXT in log {lf.name} (8-gram overlap)")
            for p in SECRET_PATTERNS:
                if p.search(text):
                    findings.append(f"SECRET PATTERN in log {lf.name}")
                    break
            # Unredacted ZDR-banned keys: the key name appears with a value
            # that is not the redaction marker.
            for key in DEFAULT_REDACT_KEYS:
                for m in re.finditer(rf'"{re.escape(key)}":\s*"([^"]{{8,}})"', text, re.I):
                    if not m.group(1).startswith("[REDACTED"):
                        findings.append(f"UNREDACTED banned key '{key}' in log {lf.name}")
                        break
    finally:
        await conn.close()

    findings = list(dict.fromkeys(findings))  # one line per finding kind
    report = {
        "zdr_check": "pass" if not findings else "FAIL",
        "checked": checked,
        "findings": findings,  # locations only — never the leaked content
    }
    print(json.dumps(report, indent=1))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
