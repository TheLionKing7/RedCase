# RedCase — Implementation Handoff

**Revision 2026-09-20 (v2).** Applied to the live repo copy. Changes: Phase 1 marked complete on evidence (G1); Phase 2 table rewritten — Slack demoted to post-deploy connector, in-app channels with agent participants take its place (Addendum §7 v2); repo layout corrected to TanStack Start; secrets registry updated to current provider reality; Phase 3 rows annotated for completed work.

**Read order (source of truth):**
1. This file — execution plan, conventions, gates
2. `docs/master-prompt.md` — governing product/architecture constraints
3. `docs/RedCase-Phase1-Design.md` → Phase 2 → Phase 3 — detailed schemas, code, checklists
4. `docs/RedCase-Feature-Addendum.md` — competitive synthesis, Workbench, monetization, comms (§7 v2 = current comms design)

**Rule: implement phases strictly in order.** Each phase has a Definition of Done (DoD) gate. Do not start Phase N+1 until Phase N's gate passes. Cross-phase shortcuts are how privilege bugs and fabricated citations ship.

**Client context:** Aetoes Legal, 3-partner Nigerian litigation firm. Aetoes is `tenant zero` of a multi-tenant SaaS. All schema is tenant-scoped from day one; only one tenant is provisioned.

---

## 1. Repository Layout (monorepo) — corrected-in-implementation

```
RedCase/
├── HANDOFF.md                    ← you are here
├── docs/                         ← design documents (source of truth; allowlisted)
├── apps/
│   ├── web/                      # TanStack Start + React + Tailwind (corrected from
│   │                             #   Next.js — deviated in implementation, recorded)
│   │   └── brand/                # RedCase SVGs (SVGO-optimize; strip #EFEFEF bg rect)
│   └── api/                      # Python 3.12, FastAPI
│       ├── app/
│       │   ├── main.py           # app factory; mounts /v1/*
│       │   ├── config.py         # pydantic-settings; NO secrets in code
│       │   ├── deps.py           # auth, tenant + user context resolution
│       │   ├── middleware/
│       │   │   ├── zdr.py        # ZDR enforcement + log redaction
│       │   │   └── audit.py      # audit writer → query_audit
│       │   ├── retrieval/        # hybrid search, gates, provider chain (make_llm)
│       │   ├── router/           # intent router + dual-vault synthesis (2.4)
│       │   ├── redteam/          # agent-chain engine + prompt packs (3.2/A/C)
│       │   ├── comms/            # channels + agent participation (2.5–2.7) — replaces slack/
│       │   ├── deadlines/        # rule pack, detection, notify (Phase 3)
│       │   └── routers/          # /v1/query, /v1/matters, /v1/documents, /v1/channels…
│       ├── scripts/
│       │   ├── ingest.py         # page-tracked ingestion (multi-series citation regex)
│       │   ├── run_battery.py    # resumable battery: --provider, --pace, provenance, 429 backoff
│       │   ├── latency_paths.py  # path-split latency from query_audit
│       │   └── zdr_audit_check.py
│       └── tests/                # pytest; see §5 testing contract
├── infra/                        # deploy artifacts (cloudrun-*.yaml, cloudflare/, GHA)
└── .github/workflows/            # CI: lint → test → migrate → deploy (production-gated)
```

**Slack connector (backlog, post-deploy):** designs preserved in Phase2 §3; requires a public URL. Do not start before deploy.

## 2. Global Conventions (non-negotiable in every phase)

1. **ZDR:** no raw document text, prompt bodies, or LLM request payloads in any log or table. Only metadata + generated outputs + citation objects persist.
2. **RLS:** every query executes with `app.tenant_id`, `app.user_ref`, `app.user_clearance` set via `SET LOCAL`. Retrieval filters live in SQL policies (RESTRICTIVE for privilege layers), never only in Python. Background jobs enumerate tenants and scope per-transaction — never bypass RLS (pattern recorded in deploy-runbook §8).
3. **Audit:** every query, upload, analysis, channel event → `query_audit` / `entitlement_events` / `signup_audit`. Append-only (per-attempt rows, no updates). Audit write failure = halt LLM responses. **Audit-then-raise pattern:** any side effect that must survive a failure (e.g. an audited DENY/refusal verdict) gets its own committed transaction boundary *before* the error is raised — raising inside the same transaction as the audit row silently rolls that row back, leaving a deny (or charge claim) with no evidence it ever happened. Applies to every audited deny path: seat gates, entitlements, conflict decisions, clearance changes. (Invited firmed in `app/routers/invites.py`; sweep RLS is the same class — effects that must survive get their own boundary.)
4. **Citations:** every generated legal proposition carries page/paragraph-pinned citations verified against the retrieved set. Fabricated citation = regenerate once, then refuse/downgrade. Never render unverified citations. Zero fabrication is a hard gate everywhere, including agent chat replies.
5. **Multi-tenant:** `tenant_id` on every table; no cross-tenant joins without explicit shared-vault flag (`vaults.is_shared`).
6. **Intake rulings:** default classification CONFIDENTIAL; PARTNER_RESTRICTED = opt-in with named grantees only (never partner-class grants); default ACL = uploader + named individuals.
7. **Brand:** crimson `#D0021B`, obsidian `#0F1115`, vellum `#E2C044`; dark UI default. Design language per `docs/design-system-guidelines.md`.
8. **Evidence rule:** every claimed measurement must be locatable as a committed artifact (file path in the report) or it is treated as unmeasured. Verbal results are anecdote.

## 3. Environment & Secrets Registry (current reality)

| Secret / var | Where | Notes |
|---|---|---|
| `SUPABASE_URL`, service-role, pooler DSN, `SUPABASE_JWT_SECRET` | `.env` now → GCP Secret Manager at deploy | Live dev project serves PAT too (decision recorded) |
| `JINA_API_KEY` (embeddings, 1024-dim v3) | `.env` → Secret Manager | Premium; corpus fully backfilled |
| `EXPLABS_API_KEY` (claude-sonnet-4.5 gateway) | `.env` → Secret Manager | Live credit; 429s handled via backoff; **ZDR toggle = owner verification item** |
| `ANSWER_MODEL_PRIMARY` / `_FALLBACK` | env config | Chain: retry same provider on 429 (max 3), hard-fail → next provider; serving provider recorded per answer in `query_audit` |
| `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY` | `.env` → Secret Manager | DeepSeek = `EXPERIMENTAL FALLBACK` (evidence: ~50% first-attempt flapping) |
| `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` | `.env` | Backlog (connector) — present, unused |
| `INTERNAL_SWEEP_TOKEN` | generated; owner pastes into GCP SM + Cloudflare worker secret | value exists nowhere in the repo |
| CI secrets (`GCP_SA_KEY`, `CF_API_TOKEN`, battery DB URL, provider keys) | GitHub Secrets | Pending owner setup |

## 4. Phase Execution Plan

### Phase 1 — Vault B Core — ✅ COMPLETE on evidence (G1 evidence complete 2026-09-19; deploy staged, PAT pending credentials)

| # | Task | Status / Evidence |
|---|---|---|
| 1.1–1.2 | Scaffold, ZDR filter, schema + RLS + tenant seed | ✅ |
| 1.3 | Page-tracked ingestion; 10-doc benchmark corpus | ✅ embeddings backfilled (Jina v3); calibration: VECTOR_GATE=0.52 (evidence-shaped; design's 0.78 refused everything under Jina — recorded) |
| 1.4–1.5 | Hybrid retrieval, `/v1/query`, citation verification, audit | ✅ battery: zero fabrications across all runs; GROUNDED_SYSTEM v2 → v2.1 (cross-chunk synthesis; causal isolation probes per version) |
| 1.6 | Web UI (refactored from Lovable MVP, TanStack Start; brand redesign; Table of Authorities; refusal panel; dev adapters) | ✅ |
| 1.7 | Deploy prep: runbook, GHA pipeline, Cloud Run target, Cloudflare DNS/cron/Access, ZDR script | ✅ artifact-complete; **deployment held pending owner credentials** (GCP SA key, Vercel connect, CF zone, CI secrets) |
| — | Latency | Path-split measured; pilot bars AMENDED with reversion trigger: answer p95 < 12s / refusal < 15s / 20s ceiling; re-assert 8s/15s at provider migration (Claude credit) or 41k scale-up |
| — | Retries | One-retry-on-refusal (refusal-only, temp 0, per-attempt audit rows); 20s answer ceiling → audited refusal |

### Phase 2 — Vault A + In-App Comms (revised: Slack → post-deploy backlog)

| # | Task | Reference | DoD |
|---|---|---|---|
| 2.1 ✅ | `clients`, `matters`, `document_grants`, clearance RLS (5 design-doc SQL corrections backported into Phase2 §1.2) | Phase2 §1.2 | Clearance battery: zero leakage at SQL level |
| 2.2 ✅ | Clearance ladder (SENIOR→CONFIDENTIAL; PARTNER_RESTRICTED grant-gated only) + envelope crypto (KeyProvider interface, local dev provider, `enc:v1`, decrypt-on-retrieve) | Phase2 §1.2, ruling | Pen-test 12/12: zero leakage, ciphertext-at-rest, tamper detection, grant_admin write policy in SQL |
| 2.3 ✅ | Vault A ingestion (CONFIDENTIAL default, named-grantee PR, hash idempotency, enc round-trip) | Phase2 §3.5 | Write-authz endpoint tests; idempotency; round-trip inversion |
| 2.4 ✅ | Dual-vault router (A/B/BOTH; namespace citations; matter-binding; ADVISORY mode) | Phase2 §2 | 60-question route set 98.3%; namespaces never mixed; refusal semantics |
| 2.5 | **In-app channels** per Addendum §7.1: `channels`, `channel_participants`, `channel_messages`; matter auto-provisioning; `comms.send` entitlement | Addendum §7 v2 | Idempotent send; non-participant = zero rows at SQL level |
| 2.6 | **Agent surfaces** per Addendum §7.2: functional agents post labeled results (battle cards, alerts) as AGENT/SYSTEM channel messages; NO mention-reply, no channel dialogue — the only conversational agent is the per-user Legal Assistant (workbench Expert Chat). Sharing an analysis into a channel is an explicit user act. | Addendum §7 v2 | Functional-post tests (labeled sender, analysis_id ref, grounding contract incl. fabrication hard gate); negative test: @mention produces no agent reply; share-to-channel path tested |
| 2.7 | Provisioning polish: `#general`, DIRECT channels, transparency feed, channel-shared doc intake rulings | Addendum §7.3 | Provisioning tests; audit parity |
| 2.8 | NDPA artifacts: RoPA (Vault A + providers incl. explabs gateway), DPIA (comms) | Phase2 §5 | Owner/counsel task |

**Gate G2:** Phase 2 §7 acceptance table green; privilege pen-test passed against live endpoints.

### Phase 3 — Workflow Intelligence + Go-Live

| # | Task | Reference | DoD |
|---|---|---|---|
| 3.1 | ~~Reranker~~ **DEFERRED with evidence** (2026-09-18): original 6 ranking-limited items recovered by GROUNDED_SYSTEM v2; revisit at 41k-corpus scale-up | Phase3 §4 | n/a — decision recorded in calibration doc |
| 3.2 ✅ | Red-Teamer engine + packs (`ADVERSARIAL_BRIEF`, `SUMMONS_RESPONSE`, `CONTRACT_REVIEW`) | Phase3 §2, Addendum §3.3 | Matcher drops planted fake citations; schema-valid outputs |
| 3.3 | Battle-card rendering — **revised**: in-channel AGENT posts + workbench UI (was: Slack renderer) | Phase3 §2.2, Addendum §4 | ADVISORY footer cannot be omitted; `[MANUAL REVIEW]` badges |
| 3.4 | Deadline rule pack (counsel-validated rows only) + detection + `deadline_events` | Phase3 §3 | Unvalidated rules disabled; synthetic order → correct due date |
| 3.5 | Notification fan-out: matter channel (§7) + Google/Outlook, daily sweep | Phase3 §3.3 | T-14/7/2/0 fire once each |
| 3.6 | Observability: metrics + self-hosted Langfuse; fabrication/critic-rate alerts | Phase3 §5.3 | Alert fire on staging injection |
| 3.7 | 5-real-case benchmark + calibration report | Phase3 §5.2 | Partners sign |
| 3.8 | Partner training + go-live checklist | Phase3 §5.4 | Sign-off recorded |
| 3.9 | **Practice operations** per Addendum §9.1: `time_entries`, `invoices`, `payments`; timer + `/time` channel capture; one-click invoicing (PDF export); receivables aging; **AI conflict check at client intake** (party names vs. Vault A + matters + corpus); trust ledger deferred (counsel-validated, Phase 4) | Addendum §9.1 | Time→invoice→payment round-trip test; conflict-check flags planted fixture conflict; synthetic data only |

**Gate G3:** Phase 3 §5.2 acceptance table green + §9.1 ops round-trip green → v1.0 live.

### Phase 4 design goals (not scheduled — Addendum §9.2)
Citator (precedent-validity graph from corpus treatments + lawyer annotations) · local-rails integrations (WhatsApp Business client channel, Paystack/Flutterwave collections — assumption-flagged, calendar/email) · review UX maturity (annotations, per-section analysis approval workflow, mobile PWA) · Judge Simulator · client portal · multi-jurisdiction packs · enterprise scale-out.

## 5. Testing Contract (applies every phase)

- **Unit:** crypto, chunker page-pinning, gates, router classification, renderers, comms idempotency.
- **Integration:** retrieval against the benchmark corpus; RLS with 3 synthetic clearances; channels with participants at different entitlements.
- **Security:** adversarial batteries each phase — privilege probing, injection strings in uploads and channel messages, grant-escalation attempts (assert denied at SQL, not app manners).
- **Regression:** the 50-question citation battery (with `--provider` provenance, pacing, 429 backoff) + 60-question router set run in CI on PRs touching retrieval/prompts/schema, once CI secrets exist.
- **Failure-mode tests:** audit-write failure halts responses; duplicate event delivery (Slack retries, idempotency keys); provider quota exhaustion → chain fallback with serving provider recorded.

## 6. Escalation

Any conflict between this handoff and the design docs → design docs win; record the correction back into the doc per rule 3 and note it in your report. Known live corrections already backported: Phase2 §1.2 SQL (RESTRICTIVE policies, qualified IDs, two-arg `current_setting`, vaults join, guard signature).
