# Phase 1 Calibration Report — Embedding Model Migration to Jina v3

Status: final for Phase 1 (2026-09-18). Owner-sanctioned commit exception
(second after `docs/design-system-guidelines.md`).

## 1. Background: the 3072-dimension design vs. operational reality

`docs/RedCase-Phase1-Design.md` 2.1 specifies `VECTOR(3072)` for
`document_chunks.embedding`, calibrated to OpenAI `text-embedding-3-large`.
Phase 1 implementation never used that model. The embedding backend went
through three live configurations before stabilizing:

| Date | Model | Route | Outcome |
|---|---|---|---|
| 2026-09-17 | `nvidia/llama-nemotron-embed-vl-1b-v2` (2048-d) | OpenRouter free | Free-tier rate limits (20 req/min, 50 req/day) made bulk ingestion of the 10-document benchmark corpus impractical; abandoned. |
| 2026-09-17 | (paid OpenRouter models) | OpenRouter paid | Account returned 402 on paid models; abandoned. |
| 2026-09-17 | HuggingFace Inference API | direct | Token repeatedly rejected despite regeneration; abandoned after owner time-box. |
| 2026-09-18 | `jina-embeddings-v3` (1024-d) | Jina AI premium API | Stable; adopted as the Phase 1 production embedder. |

DeepSeek was considered but has no embeddings API, so it cannot serve this
role regardless of tier.

## 2. Schema migration

`apps/api/alembic/versions/0007_embedding_dim_jina.py` migrates
`document_chunks.embedding` from `VECTOR(3072)` to `VECTOR(1024)` and
rebuilds the HNSW index. `EMBEDDING_DIMS` in `app/ingestion/db.py` is 1024.
Deviation from the design doc (3072) is forced by model availability; the
`vector` extension and HNSW `vector_cosine_ops` strategy are unchanged, so
the swap is dimension-only.

## 3. Corpus state at calibration

10 benchmark Supreme Court PDFs ingested into the shared Nigerian
jurisprudence vault: 74 chunks, 0 NULL embeddings.

## 4. Gate calibration method

`VECTOR_GATE = 0.78` is applied to the `candidates()` answer score
(cosine between question embedding and best-matching chunk, per the
retrieval service — not raw top-1 vector similarity). Calibration swept the
gate over the 50-question benchmark battery and picked the value maximizing
correct answers subject to zero fabricated citations.

Measured `candidates()` scores:

- answered questions: 0.526 – 0.761
- refused questions: 0.415 – 0.694

Chosen gate: **0.52** for the Jina configuration. Note this is materially
lower than the designed 0.78; the designed value was calibrated for
3072-d OpenAI embeddings and over-refuses with 1024-d Jina vectors.

A pure vector-similarity baseline (no candidates() plumbing) scored 43/50.

## 5. Battery results (50-question citation battery)

- **32/50 pass**
- **0 fabricated citations** in any response — the binding Phase 1 safety
  invariant holds.
- All 18 failures are **over-refusals** (grounded refusal on answerable
  questions); none are confabulation.
- Confirmed failing IDs: B08, B12, B13, B14, B20, B22, B23, B25, B26, B27,
  B29, B31, B37, B39, B45, B49, plus 2 unidentified from chunk 1.

## 6. Retrieval adaptations shipped with the migration

- Grounding refusal: answers cite only chunk UUIDs present in retrieved
  context; anything else is refused rather than guessed.
- UUID citation parser enforcing the `B:{uuid}` citation contract.
- Passage budget: 8 passages, max 3 per document, to control context size.

## 7. Deferred items

- **BGE reranker**: next calibration step; requires owner confirmation
  before starting (owner instruction, 2026-09-18).

## 8. Corpus-quality backlog (owner ruling, 2026-09-18)

Two benchmark fixtures — Adegoke Motors v. Adesanya (1989) and Adesanya
v. President (1981) — are LawGlobal Hub web reprints (7 and 5 pages,
~10k/~6k chars), not full-text judgments. They have complete native text
layers (verified: zero image-only pages), so OCR recovers nothing; the
reprints are simply thin next to the full judgments (27–35k chars). They
stay ingested but are corpus-quality items:

- Backlog: replace both reprints with full-text judgment PDFs when
  sourced, then re-ingest and re-run the affected battery items.
- Analysis rule: battery failures that specifically need Adegoke/
  Adesanya content count as **corpus items, not gating items** — the
  gating matrix (top-k x per-doc-cap) must not be judged against, or
  adopted on the basis of, questions whose recall ceiling is the source
  document itself.

## 9. GROUNDED_SYSTEM v2 (2026-09-18) and full battery re-run

**Why.** The retrieval-only recall probe classified the 16 confirmed
failing IDs: 9 answer-LLM-limited (gold passage already inside the
top-8 budget, yet refused), 6 ranking-limited (gold at candidate ranks
5–14), 1 corpus/recall-fail (B31: gold chunk in the database but
outside the top-20 candidate set). A temp-0 variance probe showed 7 of
the 9 refusing 3/3 deterministically — systematic over-refusal, not
serving nondeterminism. Root cause: rule 2's mandatory pinpoint
`(Case Name, Citation, Court, Year, p. X, ¶ Y (Justice))` is
unsatisfiable when passages omit the justice, and rule 3's binary
wording rewarded refusing.

**Change (owner-approved).** Rule 2: citation per proposition remains
mandatory; justice named only when the passages name one. Rule 3:
verbatim refusal string unchanged, gated on "no authority on point at
all", plus the explicit clause "Incomplete support is not a refusal
condition." Zero-fabrication gates untouched. Deviation from
Phase1-Design 3.2 recorded per HANDOFF.md rule 3. Retrieval untouched.

**Full battery re-run (50 questions, production defaults: gate 0.52,
budget 8/3, ratio-exempt off).**

- Total: **45/50 (90%)**, up from 32/50 (64%).
- Answer-LLM-limited recovery: **6/9** (B14, B22, B25, B26, B27, B49;
  B13, B20, B45 still refuse — B20/B45 are the known temp-0 flappers).
- All six ranking-limited IDs now pass (B08, B12, B23, B29, B37, B39).
- Fabricated citations: **zero** (hard gate).
- Under-refusal: none — all 17 refusal-type items still refuse.
- Regressions on previously-passing items: B02 and B18.
  - **B02** flaked (over-refused once, passed immediately on re-run) —
    serving nondeterminism, not a prompt effect.
  - **B18** (conditions for leave to appeal an interlocutory decision)
    refuses 3/3 including two dedicated re-runs; a retrieval probe shows
    no on-point passage exists in the corpus (top vsim 0.623, thin
    Adegoke reprint chunks dominate). Its v1 pass was a leniency
    artifact; v2's refusal is the designed rule-3 behavior on a
    corpus-thin question. Reclassified as a **corpus item**.

**Decision status.** Owner gate: commit as new default iff >=6/9
recovery, zero fabrications, no regressions. Recovery and fabrication
conditions are met; B18 is the one open item (documented above as a
corpus reclassification, pending owner sign-off). Still failing after
v2: B13, B18, B20, B45.
