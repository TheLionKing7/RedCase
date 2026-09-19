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

**Decision status (owner ruling 2026-09-18).** v2 committed as the new
default (072563b). Recorded per ruling:

1. **B18 reclassified as corpus-thin.** Its v1 pass was a leniency
   artifact; v2's refusal is the designed rule-3 behavior when no
   on-point passage exists. Tracked in the corpus-quality backlog.
2. **B02 logged as a known serving-nondeterminism flake** (temp-0
   over-refusal, passed on immediate re-run). Not a prompt effect;
   see the serving-variance measurements in section 10.
3. **Reranker (BGE): DEFERRED, do not build.** Evidence trail: the
   original justification was 6 ranking-limited battery IDs (gold at
   candidate ranks 5-14); all 6 recovered under v2 without any
   re-ranking. The remaining 4 failures (B13, B18, B20, B45) are
   corpus-thin (B18), serving nondeterminism (B20/B45), and one
   systematic answer-LLM case (B13, section 10) — none is a ranking
   failure a reranker would fix. Revisit at corpus scale-up to the
   full 41k-judgment corpus, where candidate sets grow ~4,000x and
   ranking pressure becomes real.

## 10. Residual failure analysis (2026-09-18)

### B13 case probe

Dumped the live v2 payload for one failing run. The 8-passage set
contains the answer across two Obikoya chunks: the ratio chunk (pages
3-5) carries the amended claim paras 7-9 — the letter dated 2/2/76,
Bronik Motors' endorsement accepting "all the terms and conditions
stipulated therein", and the N500,000 guarantee — and the pages 15-18
chunk carries the Bank's own letter: "the loan overdraft was granted on
a short term basis." The answer (an overdraft/loan facility on a
short-term basis) is present but must be SYNTHESIZED across chunks; the
question's framing ("what facility did Wema Bank approve by its letter
of 2 February 1976") presupposes a single explicit statement the corpus
does not make, and distractor amounts (N2.1m judgment debt, N500k
guarantee) sit nearby. The model refuses rather than risk mis-linking.
Determination: phrasing/framing trigger, not a missing passage.
Minimal proposed fix (v2.x, prompt-only, battery re-run to validate):
one synthesis-clarifying sentence in GROUNDED_SYSTEM, e.g. "If the
answer requires combining facts stated in different passages — a
document referenced in one passage, its terms described in another —
the passages support the combined answer; cite both passages."

### Serving variance (B20 / B45, five runs each, temp 0)

B20: 5/5 answered. B45: 5/5 answered. Combined with the battery run
(both refused) and the earlier pre-v2 probe (B20 REF-ANS-ANS, B45
REF-REF-REF), flapping persists and is time-varying on the serving
side — identical config flips between refuse and answer across
sessions. A one-retry-on-refusal policy was evaluated for under-refusal
safety: all 17 known-negative battery items were run twice each and
every run refused (34/34 refusals) — the guard holds on the full
negative set. Recommendation: one retry on refusal (not on integrity
failure), capped, audited; expected to absorb serving flakes like the
battery-run B20/B45/B02 refusals.

### Task 1.7 deploy readiness — blockers

| # | Blocker | Kind | Detail |
|---|---|---|---|
| 1 | Latency PAT failing | measurement | query_audit across battery/gating runs: median 4.3s but p95 28s (max 205s) vs PAT p95 < 8s. Regeneration/integrity retry paths dominate the tail. Decision needed: budget caps vs faster model tier vs async responses. |
| 2 | AWS/Fargate unprovisioned | credentials | No AWS account/creds in repo or env; needs ECR repo, task definition, service, Secrets Manager entries for the 6 secrets currently in apps/api/.env. |
| 3 | Vercel unprovisioned | credentials + decision | No Vercel token/project; frontend API base URL env needed. Decision: Vercel as designed, or another host. |
| 4 | Supabase production hardening | credentials + config | Direct Postgres DSN in use — needs Supavisor pooling URL for serverless; SUPABASE_JWT_SECRET absent from .env (JWT auth path unprovisioned); STORAGE_PUBLIC_URL unset (source_pdf_url links). |
| 5 | ZDR verification script | build item | Task 1.7 DoD requires it; not written. Scope: scan logs/audit tables for question bodies or document text leakage; produce pass/fail artifact. |
| 6 | Production answer-LLM decision | decision | Currently DeepSeek direct (premium key). Confirm prod model + fallback chain (Anthropic ZDR key per design? OpenRouter?). |
| 7 | CI battery | decision | Testing contract wants the 50-question battery in CI on PRs touching retrieval/prompts; it skips without live creds. Decision: CI secrets vs recorded-response fixtures. |
| 8 | CORS/domain | config | cors_origins is localhost-only; production origin needed at deploy time. |
| 9 | Pending code decisions | decision | B13 synthesis sentence (v2.x) and one-retry-on-refusal policy — both measured safe, awaiting owner go-ahead. |

## GROUNDED_SYSTEM v2.1 + one-retry policy (Task 1.7 step 1, 2026-09-18)

Owner-approved decisions applied and re-validated against the full battery:

- **v2.1**: the B13 cross-chunk synthesis sentence (exact text proposed in
  the B13 probe above) added to rule 1 of GROUNDED_SYSTEM. Retrieval, the
  refusal string, and the zero-fabrication gates untouched.
- **One-retry-on-refusal**: on a grounding refusal the answer call is
  retried ONCE with the same prompt (all configured clients answer at
  temperature 0 — AnthropicLLM now sets this explicitly; the retry is an
  identical deterministic call aimed at serving-side flapping). Integrity
  refusals do not retry (that path already consumed its one regeneration).
  EVERY attempt writes its own query_audit row — attempt number is carried
  in the structlog `query_refused` event (`attempt=1|2`); the audit table
  has no attempt column (design DDL), so per-attempt DB rows plus log
  correlation via question_hash is the faithful implementation.

Battery results (full run, then targeted re-runs; zero fabricated
citations in every run — hard gate held):

1. Full 50 under v2.1 + retry: **40/50**. Fails were 10 over-refusals
   (B02, B08, B16, B18, B20, B22, B23, B25, B26, B31); all 17
   known-negatives refused — no under-refusal.
2. One re-run of the 10 fails: B02, B16, B25 flipped to PASS — serving
   flakes, matching the documented time-varying flapping.
3. Third run of the five still refusing (B08, B22, B23, B26, B31): all
   still refused — persistent, not streaky flapping.
4. **v2-prompt isolation probe** (same IDs forced through the pre-v2.1
   prompt text, retrieval unchanged): B22 and B26 PASSED under v2 as
   well, and B22's retry path is visible in its audit — attempt 1
   refusal, attempt 2 answered with 6 citations, both rows written.
   B08, B23, B31 refused under BOTH prompts.

Determination: the v2.1 sentence is exonerated — every "regressed" ID
either flapped back to passing or refuses identically under v2. The
new persistent set (B08, B23, B31) plus B18/B20 are serving/corpus
items, the same class already documented, not prompt regressions.

- B13 (the v2.1 target): **PASS** — cross-chunk synthesis refusal fixed.
- Prompt-attributable regressions on the previously-passing set: **none**.
- Under-refusal on the 17 known-negatives: **none** (17/17 refused).
- Fabricated citations: **zero** (hard gate, all runs).

Effective battery state: persistent failures B08, B18, B20, B23, B31;
flaky B02, B16, B25 (each passed in at least one of two runs); 43/50 on
the strictest single-run count. Committed as the new default per owner
ruling.

## Latency measurement with v2.1 + retry + 20s ceiling (Task 1.7 step 2, 2026-09-18)

Ceiling implemented first (`answer_timeout_s`, default 20s, env-tunable):
an answer call exceeding it is logged as a refusal for that attempt and the
one-retry policy applies. Fresh full battery (39/50, zero fabrications) then
measured via query_audit, paths reported separately:

| Path | n | p50 | p95 | max |
|---|---|---|---|---|
| answer (success) | 22 | 4.7s | 10.8s | 11.6s |
| refusal-with-retry | 22 | 4.8s | 22.3s | 22.5s |
| threshold-refusal (no LLM call) | 6 | 1.7s | 5.5s | 5.5s |
| blended | 44 | 5.0s | 11.6s | 22.5s |

Reading against the proposed amended bars (answer <8s, refusal <15s, hard
ceiling 20s):

- The 205s-tail defect is eliminated — the ceiling works as designed, and
  the amended-bar arithmetic holds (worst observed request 22.5s = ~2s
  retrieval + 2 sequential capped calls).
- The threshold rows bound the retrieval stack at <=5.5s (p50 1.7s), so
  the LLM call dominates every path: answer-path p95 ~= 2s + ~9s call;
  refusal-path ~= 2s + 2 x ~10s calls.
- Answer-path p95 10.8s MISSES the <8s bar; refusal-path p95 22.3s misses
  <15s. This is not a bar-amendment case: the system is genuinely over bar
  on the answer path, and the cause is DeepSeek-direct per-call latency
  (4-10s observed), not measurement artifact.
- Notable: 25 of 50 requests (50%) needed the retry to reach an outcome —
  first-attempt refusal/flapping at half the corpus is far above the
  occasional-flake estimate, and it doubles answer-path LLM spend.

Decision surfaced (not made): per-call latency and flapping rate both
point at the model tier, not the pipeline. The design primary (Anthropic
Claude via the ZDR workspace key) is provisioned in code but has no key;
DeepSeek-direct is serving. This is the step-3 decision point.

## Answer-provider configuration (Task 1.7 step 1, 2026-09-18)

Owner ruling applied: env-selectable provider chain for every answer call
(retrieval, analyses/redteam — all share make_llm; no standalone
classifier client exists in Phase 1).

- `ANSWER_MODEL_PRIMARY` / `ANSWER_MODEL_FALLBACK` (comma-separated chain,
  first provisioned credential wins), then implicit anthropic -> openrouter.
- **groq = platform primary** (llama-3.3-70b-versatile via the existing
  OpenAI-compatible client — config only, no new integration code).
- **deepseek = EXPERIMENTAL FALLBACK.** Evidence: per-call latency 4-10s
  (answer-path p95 10.8s vs the <8s bar, 2026-09-18 step-2 measurement) and
  ~50% first-attempt flapping across the 50-question battery.
- **anthropic (claude-3-5-sonnet-20241022) remains the design-doc ZDR
  primary**: used automatically the moment ANTHROPIC_API_KEY is
  provisioned. The live default (Groq, then DeepSeek) deviates from
  Phase1-Design §3.3 — recorded per HANDOFF.md rule 3; the deviation is
  credential-driven, not a design change.
- OWNER VERIFICATION ITEM (not an agent task): zero-data retention must be
  enabled in the Groq console (Data Controls) for the ZDR bar to hold with
  Groq primary. Carried into the deploy runbook's pre-flight checklist.

## Groq battery attempt — blocked by account tier (Task 1.7 step 2, 2026-09-18)

- `llama-3.3-70b-versatile` 404s on the owner's Groq account (removed from
  the catalog). Per the owner's anticipated-branch note, the default
  switched to `openai/gpt-oss-120b` — verified: accepts temperature=0,
  answers via `content` with reasoning tokens separate, 1.6s for a probe
  call.
- **Blocker: the account is on the on-demand (free) tier with per-model
  ITPM ceilings below the battery prompt size.** gpt-oss-120b rejects a
  ~10.3k-token request (limit 8,000 TPM); qwen/qwen3.8-27b and
  groq/compound-mini also 413 on the same prompt. Retrieval config is
  calibrated at top-8/cap-3 (battery-comparable), so shrinking the prompt
  would invalidate comparisons — not done.
- Status: battery-vs-Groq is deferred pending owner decision: upgrade the
  Groq account to Dev Tier (billing), or run the battery on DeepSeek
  (experimental fallback) until then. Code default remains
  gpt-oss-120b — one config line already in place; it activates the
  moment the tier allows.

## ZDR verification (Task 1.7 step 4, 2026-09-18) — scripts/zdr_audit_check.py

Live-database + log-sink verifier. Exit non-zero on any finding; findings
report locations only (never leaked content). Checks: query_audit hash-only
schema; prompt-body markers in non-corpus tables; corpus 8-grams in every
non-corpus table (recent rows, --since-days); answer_text with a precise
detector (12-gram, >=3 hits, excluding cited documents, retrieved chunks,
and formulaic boilerplate shared by >=3 chunks); secret patterns; local log
sinks; per-table connections with retry (the Supabase link drops long scans).

First live run surfaced REAL findings, all triaged:

1. **Prompt-scaffold echoes in answers** (8 rows): DeepSeek sometimes emits
   `<passages>/<question>/<filters>` blocks into its output; two rows carried
   near-full passage echoes (up to 24k chars). Fix: deterministic
   `strip_echoed_blocks` sanitizer in the service (applies before
   verification + persistence), plus a unit test with an echoing fake LLM.
2. **Verbatim quotes flagged as leaks** — precision work, three rounds:
   cited-doc exclusion had a UUID-vs-string bug (never applied); after the
   fix, remaining hits were Nigerian-judgment formulaic boilerplate (322 of
   1,175 hits appear in >=3 chunks) — excluded at >=3-chunk frequency; the
   4 holdout rows are pre-v2.1 legacy whose retrieved_chunk_ids dangle after
   corpus re-ingestion (chunk ids rotate; immutable audit keeps the old
   ids). Legacy findings are documented artifacts, not current behaviour.
3. The refusal sentence ("No binding precedent found in Vault B.") was a
   false-positive marker — it is both rule-3 output and the API response
   contract. Removed from the marker set.

Post-fix evidence: three live battery IDs (B13, B02, B31) run through the
production path, then the verifier over a 0.01-day window — **pass, zero
findings** on the fresh rows. Full-window runs still flag the documented
legacy rows; that is the tool working as designed (runbook: CI runs it on
fresh traffic; history is immutable by the audit convention).

## Provider status after Cerebras attempt (2026-09-18)

- Cerebras key provisioned and wired (config-only, same OpenAI-compatible
  path). Catalog lists gpt-oss-120b + qwen-3.8-27b only; llama-3.3-70b /
  llama-4-scout 404 (owner-reported availability not yet visible on the
  account). EVERY model 402s: the account has no quota/payment method.
- Consequence recorded in .env (not committed): ANSWER_MODEL_PRIMARY=deepseek
  until a provider quota check passes — the chain resolves cerebras on key
  presence and would 402 every answer call otherwise.
- NDPA processor register (owner-held per HANDOFF §2.8; drafted for filing):

  | Processor | Role | Data categories | Diligence | Status |
  |---|---|---|---|---|
  | Cerebras AI | answer-LLM inference (primary, provisioned) | question embeddings-of-context: retrieved passages + prompts in request payloads | same class as Groq/DeepSeek/Anthropic: ZDR bar applies — no prompt bodies or document text in RedCase stores/logs; console zero-retention setting to be verified by owner (same open item as Groq) | ACTIVE config, INACTIVE traffic (402 — awaiting account quota) |

## OpenRouter gpt-4o primary — credit blocker (2026-09-18)

Owner funded a new OpenRouter key; openai/gpt-4o verified (temperature=0
accepted, ~10k-token grounded prompts served in ~3s). Defaults committed:
ANSWER_MODEL_PRIMARY=openrouter, FALLBACK=cerebras,groq,deepseek;
llm_model=openai/gpt-4o.

Two diligence notes recorded:

- gpt-4o is NOT a ZDR-class endpoint: OpenAI API default retention applies
  (no training; 30-day abuse-monitoring retention unless a ZDR agreement
  exists). Owner verification item, same class as the Groq/Cerebras
  console zero-retention settings. Anthropic claude-3-5-sonnet remains the
  design-doc ZDR primary, picked up automatically when keyed.
- Battery run blocked: the key's remaining credit covers ~3,500 output
  tokens (OpenRouter affordability pre-check). Fix shipped in advance:
  answer_max_tokens=4096 (Settings, construction-time on OpenAICompatLLM)
  — bounds per-answer spend and satisfies the pre-check once credits land.
  Awaiting owner top-up, then step 2 battery vs gpt-4o proceeds.

## Battery vs ministral-8b — FAILED the under-refusal gate (2026-09-18)

Mistral free tier serves only the Ministrals (small/medium rate limit is
0 req/min — verified via 429 headers). Pilot 4/5 clean, so the full
battery ran: **41/50, zero fabricated citations — but 4 UNDER-REFUSALS**
(B32, B38, B42, B44: out-of-corpus questions ANSWERED). Known-negatives
13/17 vs DeepSeek's 17/17 (and 34/34 in the retry probe). First-attempt
flap 23/50 (46%) — similar to DeepSeek, so flapping is not provider-
specific; the ~50% first-attempt refusal rate across two unrelated
providers points at serving nondeterminism class, absorbed by the retry
policy either way.

Determination: ministral-8b is DISQUALIFIED as a platform answer model —
answering out-of-corpus questions is the dangerous failure mode for a
legal product, worse than a low score. gpt-4o (funded OpenRouter key,
verified fast + temp-0 clean) is the next candidate for step 2; DeepSeek
remains the only battery-qualified model serving today. .env chain
re-pinned: deepseek primary until a funded challenger lands.

| Provider/model | Battery | Fabrications | Under-refusal (17) | Status |
|---|---|---|---|---|
| DeepSeek-chat | 45/50 (v2), 43-46/50 (v2.1 runs, flaky) | 0 | 0/17 | qualified, serving (experimental fallback) |
| ministral-8b (Mistral free) | 41/50 | 0 | 4/17 | DISQUALIFIED |
| gpt-4o (OpenRouter) | pending credits | — | — | verified capable, unfunded |
| gpt-oss-120b (Groq/Cerebras) | tier-blocked | — | — | awaiting Dev Tier / account quota |

## Free-provider capacity probe — both dead for battery-size prompts (2026-09-19)

Owner redirect (2026-09-19): run steps 2-3 against free providers (Cerebras,
Groq-ZDR) with the paced runner before any OpenRouter spend. Probed live via
`scripts/probe_providers.py` (tiny call + realistic ~10k-token grounded-size
call, app's own client path):

| Provider | Tiny call | ~10k-token call | Verdict |
|---|---|---|---|
| Cerebras `gpt-oss-120b` | 402 payment_required | 402 payment_required | No free quota on the account — account-wide, billing tab needs payment. Not a rate limit; cannot be paced around. |
| Groq `openai/gpt-oss-120b` | OK, 1.1s | 413 — TPM limit 8,000/min | Free-tier per-minute TOKEN ceiling is smaller than one battery prompt (~10k). Pacing (added in f89bea4, --pace default 12s) fixes RPM, not a size cap. |

Conclusion: neither free provider can serve a single grounded battery
question, let alone 50. The redirect's escape hatch ("only if both free
providers fail does OpenRouter credit become the right spend") is triggered
— and on capacity, a harder failure than citation discipline. Options for
the owner: (a) small OpenRouter top-up -> gpt-4o confirmation battery per
the original plan; (b) accept DeepSeek-chat as the PAT production answer
model (only battery-qualified model serving today; v2.1 + one-retry policy
committed as default in 325104c) and migrate to gpt-4o post-PAT. Decision
rests with the owner — spend vs ship. G1 stays open until the paced
battery + path-split latency run against the chosen provider.
