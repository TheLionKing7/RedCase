"""Audit writer (Task 1.5, Phase1-Design §2.1 query_audit; HANDOFF.md 2.3).

Contract:
- Every query writes exactly one query_audit row (refusals included) with
  metadata only: question SHA-256 (never the question text), filters, chunk
  ids, similarity scores, threshold_passed, answer_text (generated output IS
  auditable per the DDL comment), citations, latency.
- An audit-write failure must HALT the response: exceptions propagate to the
  caller, which maps them to a 500. Never swallow, never retry-silently.
- RLS: query_audit carries tenant_id; the migration chain adds tenant_isolation
  (HANDOFF.md 2.5 tenant scoping — see 0002 migration; §2.1's DDL omitted the
  policy, recorded as a design conflict in that migration).
"""

import json
import uuid
from typing import Any

import asyncpg

from app.middleware.zdr import get_logger

log = get_logger("redcase.audit")

AUDIT_SQL = """
    INSERT INTO query_audit
        (id, tenant_id, user_ref, question_hash, filters, retrieved_chunk_ids,
         similarity_scores, threshold_passed, answer_text, citations,
         latency_ms, analysis_id, serving_provider, serving_model)
    VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8, $9, $10::jsonb, $11, $12, $13, $14)
"""


async def write_audit(db: asyncpg.Connection, audit: dict[str, Any]) -> None:
    """Persist one query_audit row. Raises on failure — by design (HALT).
    ``analysis_id`` links analysis-pipeline events (Feature-Addendum Step A);
    null for /v1/query traffic. ``serving_provider``/``serving_model`` record
    which provider actually served the answer (fallback chain) — null for
    threshold-only refusals that never reach an answer LLM."""
    await db.execute(
        AUDIT_SQL,
        uuid.uuid4(),
        uuid.UUID(str(audit["tenant_id"])),
        audit["user_ref"],
        audit["question_hash"],
        json.dumps(audit.get("filters") or {}),
        list(audit.get("retrieved_chunk_ids") or []),
        list(audit.get("similarity_scores") or []),
        bool(audit.get("threshold_passed", False)),
        audit.get("answer_text"),
        json.dumps(audit.get("citations") or []),
        int(audit.get("latency_ms") or 0),
        uuid.UUID(str(audit["analysis_id"])) if audit.get("analysis_id") else None,
        audit.get("serving_provider"),
        audit.get("serving_model"),
    )
    log.info(
        "query_audited",
        question_hash=audit["question_hash"],
        threshold_passed=bool(audit.get("threshold_passed", False)),
        latency_ms=audit.get("latency_ms"),
    )
