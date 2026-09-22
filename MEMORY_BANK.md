# RedCase — MEMORY BANK

> **Purpose:** A single, localized synchronization point so subsequent tasks understand the workspace layout WITHOUT re-reading every code file from scratch. Read this first. Update it after any schema/architecture/test change.
>
> **Source-of-truth hierarchy (per HANDOFF.md §6):** design docs win over HANDOFF.md; HANDOFF.md wins over code. Record every live correction back into the doc.
>
> **Primary docs (read order):** `HANDOFF.md` → `docs/master-prompt.md` → `docs/RedCase-Phase1-Design.md` → `...Phase2/Phase3...` → `docs/RedCase-Feature-Addendum.md`.

**Client context:** Aetoes Legal, 3-partner Nigerian litigation firm = `tenant zero` of a multi-tenant SaaS. All schema is tenant-scoped from day one.

---

## [System Architecture]

High-level request flow, front to back:

```
apps/web (TanStack Start + React + Tailwind, port 7100 dev)
    │  typed fetch client (apps/web/src/lib/api/client.ts) → Bearer Supabase JWT
    ▼  VITE_API_BASE_URL (default http://127.0.0.1:8000)
apps/api (FastAPI, Python 3.12, port 8000)
    │  main.create_app() — app factory, mounts /v1/* routers
    ▼
  deps.get_tenant_context() — verifies Supabase HS256 JWT (shared secret),
    opens one asyncpg connection in a txn, sets RLS GUCs:
      app.tenant_id, app.user_ref, app.user_clearance  (SET LOCAL, per-request)
    yields TenantContext(tenant_id, user_ref, clearance, db)
    ▼
  entitlements.require_feature(feature) — optional gate dependency.
    Writes exactly one entitlement_events row; DENY_PLAN/DENY_SEAT→402,
    DENY_SUSPENDED→403. Premium set = {workbench.analyze, workbench.chat, workbench.assistant}.
    Core features (core.dual_vault, comms.send, ops.time) always ALLOW but still audit.
    ▼
  Routers (apps/api/app/routers/*) → service/engine layers →
  Postgres (asyncpg pool, RLS enforced in SQL policies, NOT only in Python)
```

**Key invariants (HANDOFF §2, non-negotiable):**
1. **ZDR** — no raw doc text / prompt bodies / LLM payloads in logs or tables. Only metadata + outputs + citations persist.
2. **RLS** — every query scoped by `app.tenant_id/user_ref/user_clearance`; filters live in SQL policies (RESTRICTIVE for privilege layers), never only in Python. FKs bypass RLS → routes validate tenancy explicitly before inserts referencing other-tenant rows.
3. **Audit** — every query/upload/analysis/channel event → `query_audit`/`entitlement_events`, append-only; audit-write failure halts LLM responses.
4. **Citations** — every legal proposition carries page/paragraph-pinned citations verified against the retrieved set; fabricated citation = regenerate once, then refuse. Zero fabrication is a hard gate.
5. **Multi-tenant** — `tenant_id` on every table; no cross-tenant joins without shared-vault flag.
6. **Intake ruling** — default classification CONFIDENTIAL; PARTNER_RESTRICTED = opt-in named grantees only; default ACL = uploader + named individuals.

---

## [File & Nerve Map]

### Backend — `apps/api/app/`

| File/Dir | Responsibility |
|---|---|
| `main.py` | App factory `create_app()`; lifespan opens asyncpg pool (`state.db_pool`); mounts all routers under `/v1`; CORS; `GET /v1/health`. |
| `config.py` | pydantic-settings `Settings`, `get_settings()` (lru_cache). **NO secrets in code** — all env-backed SecretStr. Brand tokens. Embedding/answer-model provider chain + thresholds (VECTOR_GATE=0.52, top_k=8, per_doc_cap=3, answer_timeout_s=20, max_tokens=4096). `require_secrets()` fails fast. |
| `deps.py` | `get_tenant_context` dependency, `TenantContext` dataclass, `verify_supabase_jwt` (HS256). Sets RLS GUCs per-request. Auth = Supabase email magic-link JWT. |
| `entitlements.py` | `require_feature(feature)` dependency factory; `PREMIUM_FEATURES`; writes `entitlement_events` DECISION rows; 402/403 with upgrade copy. |
| `schemas.py` | Shared Pydantic wire models. |
| `routers/` | FastAPI route modules (see table below). |
| `middleware/zdr.py` | structlog config + ZDR redaction filter; `get_logger`. |
| `middleware/audit.py` | Audit writer → `query_audit`. |
| `retrieval/` | `clients.py` (provider clients + `make_llm`), `service.py` (hybrid retrieve + gates), `prompts.py` (GROUNDED_SYSTEM v2.1). |
| `router/` | `service.py` — intent router + dual-vault synthesis (`dual_vault_query`, Mode), matter-binding, refusal rules. |
| `redteam/` | `engine.py` (agent-chain), `packs.py` (ADVERSARIAL_BRIEF/SUMMONS_RESPONSE/CONTRACT_REVIEW), `schemas.py`. |
| `comms/` | `agents.py` — functional agent participants posting AGENT/SYSTEM channel messages (battle cards). |
| `ingestion/` | `chunker.py` (page-tracked), `db.py`, `metadata.py`. |
| `invoicing_pdf.py` | Invoice PDF builder (3.9 sub-task 2) — pymupdf A4 letterhead using brand tokens (crimson/obsidian/gold) as 0-1 RGB; `InvoiceLine` dataclass; NGN money formatting; subtotal/paid/balance block. |
| `vault_a/` | `crypto.py` (KeyProvider, enc:v1 envelope), `ingest.py`. |

### Routers — `apps/api/app/routers/`

| Router | Prefix / Endpoints | Notes |
|---|---|---|
| `query.py` | `/v1/query` | Vault B hybrid retrieval Q&A. |
| `router.py` | `POST /v1/dual/query` | Dual-vault query; gated `core.dual_vault`; calls `router.service.dual_vault_query`. |
| `analyses.py` | `/v1/analyses`, `/v1/analyses/{id}` | Workbench pack analyses (AnalysisStatus wire model). |
| `channels.py` | `/v1/channels`, `/v1/channels/{id}/messages`, `POST /v1/channels/{id}/messages` | In-app channels (2.5/2.6). Includes `/time <minutes> <desc>` slash-command → `time_entries` on the channel's matter + reflects a message. Attachment tenancy checks (FK bypass). Direct channels via `provision_direct_channel` SECURITY DEFINER. |
| `expert_chat.py` | Workbench Expert Chat (3.1) | Per-user conversational assistant. |
| `assistant/` | **Legal Assistant (Addendum §7.2)** — the ONE conversational agent. `service.py` = `run_assistant_turn` bounded ReAct loop (planner→executor→verifier, `MAX_TOOL_ITERATIONS=6`) with internal tools `search_vault_a`/`search_vault_b`/`matter_context`/`save_to_workbench`/`analyze_document`; grounding via `verify_namespaced_citations` (zero-fabrication hard gate), serving provider recorded. `router.py` = `/v1/assistant/threads`, `GET /threads/{id}` (turns + digest), `POST /threads/{id}/messages` (SSE), `POST /threads/{id}/feedback` (learning signal → `style_correction` preference). |
| `internal.py` | Internal/sweep endpoints | Token-gated. |
| `audit.py` | Audit read endpoints | |
| `vault_a.py` | Vault A routes | Clearance-gated ingestion/retrieval. |
| `practice.py` | `POST/GET /v1/matters/{matter_id}/time` | Time capture (3.9 sub-task 1). `ops.time` CORE entitlement; matter tenancy validated; idempotency on (tenant_id, idempotency_key); minutes>0; returns total_minutes. |
| `invoicing.py` | `POST /v1/matters/{id}/invoice`, `GET /v1/matters/{id}/invoices`, `GET/POST /v1/invoices/{id}`, `POST /v1/invoices/{id}/send`, `GET /v1/invoices/{id}.pdf`, `POST /v1/invoices/{id}/payments`, `GET /v1/receivables/aging` | Invoicing + payments (3.9 sub-task 2). `ops.invoicing` premium gate; per-tenant `RC-<N>` numbering; line amount = minutes/60 × hourly rate_ngn; DRAFT→SENT (send, `sent_at`), payment → PARTIAL/PAID; PDF via `app.invoicing_pdf` (pymupdf, brand letterhead); aging buckets for receivables. |
| `_load_invoice` helper | (in invoicing.py) | Fetches invoice + `paid_ngn`/`balance_ngn` + optional lines; 404 on foreign/unknown. |


### Migrations — `infra/supabase/migrations/versions/`

Sequential `0001`…`0017`:
`0001_phase1_core`, `0002_query_audit_rls`, `0003_workbench_tables`, `0004_entitlements`, `0005_channels`, `0006_embedding_2048`, `0007_embedding_1024_jina`, `0008_vault_a_clearance`, `0009_clearance_ladder`, `0010_provider_provenance`, `0011_channels_v2`, `0012_agent_participation`, `0013_expert_chat_thread`, `0014_time_entries`, `0015_invoicing`, `0016_conflict_check`, `0017_assistant`.
- `0014_time_entries.py`: `time_entries` (tenant_id, matter_id FK→matters, user_ref, description, minutes>0, rate_ngn, billed, idempotency_key, created_at, worked_at) + (tenant_id, matter_id) idx + unique (tenant_id, idempotency_key) idx + RLS tenant_isolation.
- `0015_invoicing.py`: `invoices` (tenant_id, matter_id, number, status DRAFT/SENT/PARTIAL/PAID, amount_ngn, due_date, sent_at, created_at) + `invoice_line_items` (snapshot of each billed entry) + `payments` (invoice_id, amount_ngn, method, received_at) + RLS on all three. Per-tenant `RC-<N>` invoice number sequence.

### Tests — `apps/api/tests/` (pytest)

`conftest.py` (fixtures/app factory), `pdf_factory.py`, plus `test_app`, `test_query_api`, `test_router`, `test_retrieval`, `test_citation_battery` (50-q), `test_channels`, `test_agents`, `test_practice`, `test_invoicing`, `test_provisioning`, `test_entitlements`, `test_analyses`, `test_expert_chat`, `test_clearance`, `test_privilege_pentest`, `test_rls`, `test_zdr_filter`, `test_chunker`, `test_ingest_db`, `test_metadata`, `test_internal`, `test_packs`, `test_provider_fallback`, `test_vault_a_ingest`.

### Frontend — `apps/web/src/`

| File | Responsibility |
|---|---|
| `router.tsx` / `routeTree.gen.ts` / `start.ts` / `server.ts` | TanStack Start bootstrap + generated route tree. |
| `routes/` | `__root.tsx` (root layout + error/not-found), `index.tsx` (marketing home). **Auth boundary (Part 3 S1):** `_authed.tsx` pathless layout guard (no session → redirect `/signin`; bypass when `VITE_API_DEV_ADAPTER=1`) wraps `_authed.search.tsx`, `_authed.tracker.tsx`, `_authed.red-teamer.tsx`, `_authed.workbench.tsx`. Public: `signin.tsx` (password + magic-link), `accept-invite.tsx` (`?token=` sets password → activates seat). |
| `components/AppShell.tsx` | App chrome (navigation + brand). |
| `components/ui/*` | shadcn/ui-style primitives (button, card, dialog, tabs, …). |
| `lib/api/client.ts` | Typed `apiPost`/`apiGet` fetch client; forwards Bearer Supabase JWT; `ApiError`; base `http://127.0.0.1:8000`/`VITE_API_BASE_URL`. |
| `lib/api/workbench.ts` | `useAnalyses`/`useAnalysis` → `/v1/analyses`, `Analysis` (wire mirror of AnalysisStatus). |
| `lib/api/query.ts`, `deadlines.ts`, `redteam.ts`, `types.ts` (+ `dev/*` adapters) | Other typed API modules + dev adapters. |
| `lib/auth/supabase.ts` | Minimal Supabase Auth HTTP client: `signInWithEmail` (OTP magic link), `verifyOtp`, `signInWithPassword` (Part 3 S1), `getSession`, `getAccessToken`, `getClearance` (decodes JWT `app_metadata.clearance`, fails closed to STAFF), `signOut`. |
| `lib/court-filters.ts`, `error-page.ts`, `utils.ts` | Helpers. |
| `styles.css` | Tailwind + brand theme (dark default). |

### Docs — `docs/`
`master-prompt.md`, `RedCase-Phase1/2/3-Design.md`, `RedCase-Feature-Addendum.md` (§7 comms v2, §9.1 practice ops), `deploy-runbook.md`, `design-system-guidelines.md`, `MVP-Audit-Refactor-Plan.md`, `RC-BrandTheme.md`, `explabs_coding_probe.py`.

7. **Brand** — crimson `#D0021B`, obsidian `#0F1115`, vellum `#E2C044`; dark UI default.
8. **Evidence** — every claimed measurement must be a committed artifact (file path) or it is unmeasured.

---

## [State of Play]

**Branch:** `main` (ahead of origin — NOT pushed).

### Completed
- **Phase 1 — ✅ COMPLETE (G1 evidence 2026-09-19):** scaffold, ZDR filter, schema+RLS+seed, page-tracked ingestion (Jina v3, VECTOR_GATE=0.52), hybrid retrieval + `/v1/query` + citations + audit, Web UI (TanStack Start, brand redesign), deploy prep (held pending owner credentials).
- **Phase 2 (in-app comms; Slack deferred to post-deploy):**
  - 2.1 ✅ clients/matters/document_grants/clearance RLS; 2.2 ✅ clearance ladder + envelope crypto (12/12 pen-test); 2.3 ✅ Vault A ingestion; 2.4 ✅ dual-vault router (98.3%); 2.5 ✅ in-app channels (`dec4c5f`); 2.6 ✅ agent surfaces (`d54e8e6`); 2.7 ✅ provisioning polish (`4a54da9`).
- **Phase 3:**
  - 3.1 ✅ Expert Chat backend (`8a8e2a1`); 3.2 ✅ Red-Teamer engine + packs (`842146b`).
  - **3.9 sub-task 1 ✅ JUST COMPLETED** — practice time capture (practice.py, channels.py `/time` command, main.py mount, test_practice.py, 0014_time_entries). **Committed `60c22bf`**; tests pass, ruff clean.
  - **3.9 sub-task 2 ✅ COMPLETED** — invoicing + payments (invoices, invoice_line_items, payments; invoicing.py router wired in main.py; invoicing_pdf.py brand letterhead; 0015_invoicing; test_invoicing.py 6/6 pass). Committed below.
  - 3.9 sub-task 2 deviations recorded in `0015_invoicing.py` header: line-items table added, `sent_at` added, explicit tenant_id on payments, RLS on all 3 (per HANDOFF 2.5).
  - **3.9 sub-task 3 ✅ COMPLETED** — AI conflict check at client intake (`conflict_matcher.py` three-tier matcher EXACT/FUZZY/PHONETIC; `routers/conflicts.py` POST /conflicts/check / GET /conflicts/{id} / POST /conflicts/{id}/decision append-only; scans clients/matters/Vault A case_title; gated require_feature("ops.conflicts") CORE; wired in main.py; `0016_conflict_check.py`). `tests/test_conflicts.py` 7/7 pass; **alembic ids fixed** (`revision`/`down_revision` lowercase).
- **Legal Assistant (Addendum §7.2) ✅ COMPLETED** — `app/assistant/` (bounded ReAct agent, `service.py` + SSE `router.py`), `PREMIUM_FEATURES` += `workbench.assistant`, `0017_assistant.py` (threads/messages/preferences/feedback/artifacts + tenant+user RLS single PERMISSIVE policies — RESTRICTIVE blocks app-role inserts, verified). Tests: entitlement gate 402/200, thread flow, SSE+persistence, feedback→preference→prompt round-trip, zero-fabrication refusal, bounded loop cap.

### In Progress / Next
- **Part 1 — Marketing website (in progress)** — `/` is now the public marketing landing; Vault Search relocated to `/search` (route `search.tsx`, export renamed `SearchPage`); AppShell nav `/`→`/search` (lines 6/55/118). New `src/components/marketing/` = MarketingLayout (sticky nav + footer + Eyebrow), Hero (uses SplitVaultVisual), SplitVault (Vault A/B + Juris 41,902 + skeleton shimmer), Problem, DualVault, Trust, RedTeam (adversarial battle-card artifact), SecureMessenger (chat-thread mock), Workbench (SmartBrief pipeline — renamed from BriefBot), Operations, Security, Pricing, Receptionist (chat panel grounded ONLY on `src/data/receptionist-knowledge.json`; off-corpus → "I don't want to guess — let me connect you." + Talk-to-us; pricing → "Talk to us."; purely local, nothing persisted / no network). **Receptionist converted from full-width `<section>` to a fixed bottom-right floating chat widget** — `Headset` launcher button (z-50, crimson gradient, gold ring, pulsing online dot), collapsible `panel`-styling aside (`surface` + `shadow-elevated`), auto-scroll via ref, suggestion chips, escalate notice, ephemeral no-network footer. Det left `answer()` classifier byte-preserved; added `[price|...]` guard → "Talk to us." and capability/citation encryption fallbacks. Em-dashes written as real UTF-8 (no BOM); tsc-clean for Receptionist; `npm run build` GREEN. Faq.tsx deleted (answers live in the knowledge file). Favicon→`/brand/redcase-mark-crimson.svg`. Brand SVGO-optimized in `apps/web/brand/` + `public/brand/`. `ADVERSARIAL_BRIEF` code constant untouched (display-only rename). Next: commit per repo conventions.
- **Part 2 — Onboarding growth surface (public signup + verify + firm invite) ✅ COMPLETED** — `app/onboarding.py` (ROLE_TO_CLEARANCE ladder — ASSOCIATE→STAFF floor; normalize_email; hash_verify_token; new_verify_token); `app/rate_limit.py` (PublicSignupLimiter, per-IP + per-email sliding window); `app/routers/signup.py` (POST `/v1/public/signup` unauthenticated+rate-limited, POST `/v1/public/verify` — constant-time token check, provisions tenant+vault+CORE sub max_seats=3 in one txn w/ RLS, flips ACTIVE, clears token, verify/provision/activate audit rows); `app/routers/invites.py` (POST `/v1/invites` PARTNER/ADMIN-only, seat-gated — 402 DENY_SEAT at capacity w/o increment, atomic seat consume otherwise, ASSOCIATE→STAFF+PARTNER→PARTNER clearance, 'invite'/'invite_denied' audit). Migration `0018_public_signup.py` = firm_signups/signup_audit/firm_invites. `main.py` mounts both routers + `PublicSignupLimiter` app state. `tests/test_signup_invites.py` fully rebuilt (signup + verify + invites classes, **12 tests**), ruff-clean, paths `/v1/public/signup`+`/v1/public/verify`. **TEST RUN (via project venv): full suite `212 passed, 51 skipped, 0 failed`.** Two real bugs found & fixed while running against embedded PG: (1) the DENY verdict previously raised HTTPException INSIDE its transaction → rolled back the `invite_denied` audit row; refactored to commit the DENY audit in its own txn then raise, and re-set the `app.tenant_id` GUC in the credit txn (is_local=true reset it to "" → `""::uuid` cast error). (2) asyncpg is loop-bound — test DB helpers must run all async work in one `asyncio.run()` per connection lifecycle and set the GUC inside a `conn.transaction()` before reading RLS-scoped tables. **ENV CAVEAT:** `pgserver` cannot be installed by global pip (network-restricted) — **use the repo's project venv `apps/api/.venv` which already has it; do NOT reinstall.**
- **Task 3.9 sub-task 3+ (Addendum §9.1):** payments UI + receivables dashboard (frontend remains). Conflict check backend ✅. Trust ledger deferred (Phase 4).
- **Part 2 DoD commit ✅** — committed `25da33e` `fix(onboarding): invite DENY audit rollback + GUC reset; signup/invite suite green (12/12, full 212/0)` (bundled Legal Assistant companion `app/assistant` + migration 0017 + test_assistant.py so `main.py` wiring builds). HANDOFF.md Audit convention now records the **audit-then-raise pattern** (side effects that must survive get their own txn before the error is raised). Pushed to **origin** (all 92 local commits).
- **Part 3 Slice 1 — Auth Boundary ✅ (build green)** — `_authed` pathless layout wraps `/search`,`/red-teamer`,`/tracker`,`/workbench` (routes renamed `_authed.*`, flat routing); beforeLoad guard: no Supabase session → redirect `/signin`, bypass when `VITE_API_DEV_ADAPTER=1`, SSR-safe (client-only localStorage check). New public routes `/signin` (password grant + magic link via `signInWithPassword`/`signInWithEmail`) and `/accept-invite?token=` (validates token → sets password → activates seat; `lib/api/accept-invite.ts` + dev adapter). `lib/auth/supabase.ts` gains `signInWithPassword` + `getClearance()`. `.env.example` documents `VITE_API_DEV_ADAPTER`.
- **Part 3 Slice 1 backend close — POST /v1/invites/accept ✅ (suite green 216/51)** — migration `0019_invite_accept.py` adds `invite_token_hash` (UNIQUE) / `invite_token_expires_at` / `accepted_at` / `accepted_user_ref` / `accepted_clearance` to `firm_invites`, plus a **SECURITY DEFINER** `redcase_claim_invite(token_hash, now)` that atomically flips a PENDING invite → ACCEPTED (single-use enforced in SQL with `status='PENDING'`; lookup bypasses RLS so the unauthenticated path can learn the tenant from a token — no tenant JWT exists here). `app/onboarding.py` gains `new_invite_token`/`hash_invite_token` (separate subkey namespace). `rate_limit.py` gains `InviteAcceptLimiter` (per-IP + per-token), wired in `main.py`; config gains `invite_accept_rate_*` + `invite_token_ttl_s` (7d). `create_invite` now generates a token and returns it (raw) in the 201 body for the invite link. `accept_invite`: rate-limited, uniform 400 on unknown/used/expired; clearance derived **server-side** from the invite role mapping (client `clearance` field ignored — fail-closed); Supabase Admin API (`/auth/v1/admin/users`) sets `app_metadata {tenant_id, clearance}`; on user-creation failure the invite is re-opened (PENDING); audit `invite_accepted` row written (token hash, email, clearance, tenant). Tests: `TestInviteAccept` (4 tests) — happy path + single-use + expired + clearance-injection-ignored; exercises Supabase via monkeypatch (no service role in CI). **ZDR note (intentional, spec-mandated):** the `invite_accepted` audit `detail` includes the invited email — a documented exception to the "no PII in audit" convention. **Next:** Slice 2 — role landing by clearance (PARTNER/ADMIN → firm dashboard compose; SENIOR/ASSOCIATE/STAFF → workbench).

- **Phase 3 remaining:** 3.3 battle-card rendering, 3.4 deadline rule pack (`deadlines/` module NOT YET created), 3.5 notification fan-out, 3.6 observability/Langfuse, 3.7 benchmark+calibration, 3.8 training/go-live.
- **Backlog:** Slack connector (post-deploy), deadline sweeps, reranker (deferred with evidence).
- **Blocker:** Phase 1 deploy held pending owner credentials (CI secrets, GCP SA, CF zone).

### Working-tree notes
- `MEMORY_BANK.md` + `.gitignore` negation committed (`4dc9bb4`); the `.md` ignore now exempts MEMORY_BANK.md so future commits need no force-add.
- `MEMORY_BANK.md` file tracks current intent; **drift caveat applies** — run `git status` before assuming the map is current.
- Uncommitted: `HANDOFF.md`, `apps/web/public/brand/redcase-mark-white.svg`, `docs/RedCase-Phase1/Phase3-Design.md` (design backport docs), plus calibration artifacts.

---

## [Operational Notes]
- **Frontend:** TanStack Start (NOT Next.js — deviated, recorded).
- **Backend:** FastAPI, async/await, asyncpg, raw SQL (no ORM); migrations via Alembic-style `op.execute`.
- **Quality gates:** ruff clean; `pytest` in `apps/api`.
- **Env:** Windows/PowerShell — `&&` does NOT work; use `;` or separate commands.
- **Update rule:** after modifying files, running tests, or changing schema, update this file immediately.
- **Drift caveat:** Uncommitted/untracked drift is not reflected here; run `git status` before assuming the map is complete.

