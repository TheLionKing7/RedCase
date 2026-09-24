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
| `kyc.py` | `GET/POST /v1/firm/kyc` | Firm KYC (S10-1). Gated by `deps.require_firm_admin` (orthogonal `is_firm_admin` JWT flag). Upsert with PENDING reset; ops-only VERIFIED/REJECTED. Store refs/paths only (PARTNER_RESTRICTED-class). |
| `matters.py` | `POST /v1/matters/{id}/assign`, `GET /v1/matters/{id}`, `GET /v1/matters/my`, `GET /v1/firm/matters/progress` | Matter assignment (S10-3). Assign requires PARTNER/ADMIN clearance or firm-admin; assignee must be a licensed firm user (ACCEPTED firm_invite); `/my` filters `assigned_to = me`; progress panel composes EXISTING data (analyses_count + time_minutes) gated by `require_firm_admin`. |


### Migrations — `infra/supabase/migrations/versions/`

Sequential `0001`…`0017`:
`0001_phase1_core`, `0002_query_audit_rls`, `0003_workbench_tables`, `0004_entitlements`, `0005_channels`, `0006_embedding_2048`, `0007_embedding_1024_jina`, `0008_vault_a_clearance`, `0009_clearance_ladder`, `0010_provider_provenance`, `0011_channels_v2`, `0012_agent_participation`, `0013_expert_chat_thread`, `0014_time_entries`, `0015_invoicing`, `0016_conflict_check`, `0017_assistant`, `0018_public_signup`, `0019_invite_accept`, `0020_firm_admins`, `0021_firm_kyc`, `0022_practice_areas_personas`, `0023_matter_assignment`.
- `0014_time_entries.py`: `time_entries` (tenant_id, matter_id FK→matters, user_ref, description, minutes>0, rate_ngn, billed, idempotency_key, created_at, worked_at) + (tenant_id, matter_id) idx + unique (tenant_id, idempotency_key) idx + RLS tenant_isolation.
- `0015_invoicing.py`: `invoices` (tenant_id, matter_id, number, status DRAFT/SENT/PARTIAL/PAID, amount_ngn, due_date, sent_at, created_at) + `invoice_line_items` (snapshot of each billed entry) + `payments` (invoice_id, amount_ngn, method, received_at) + RLS on all three. Per-tenant `RC-<N>` invoice number sequence.
- `0021_firm_kyc.py` (S10-1): `tenants.logo_path` column; `firm_kyc` (id, tenant_id UNIQUE→tenants, cac_number, rc_document_path, admin_id_type, admin_id_document_path, id_document_type, firm_website, verification_status CHECK PENDING/VERIFIED/REJECTED DEFAULT PENDING, submitted_at, reviewed_by, reviewed_at) + tenant-scoped RLS + firm-admin gate (reads `app.is_firm_admin` GUC); `redcase_app` GRANTs in idempotent `pg_roles` guard. Storage-refs only (docs stay in private bucket; PARTNER_RESTRICTED-class).
- `0023_matter_assignment.py` (S10-3): `matters.assigned_to TEXT` + `matters.progress_note TEXT` columns; index `matters_assigned_idx (tenant_id, assigned_to)`; recreated `tenant_isolation` policy ON matters WITH **WITH CHECK** (0008 granted only USING → UPDATE blocked app-role writes). ZDR: ref id + firm op content only. (`0022_practice_areas_personas.py` = S10-2, not listed here — see SLICE 2 entry + practice_areas/user_personas + legal_topics lens.)

### Tests — `apps/api/tests/` (pytest)

`conftest.py` (fixtures/app factory), `pdf_factory.py`, plus `test_app`, `test_query_api`, `test_router`, `test_retrieval`, `test_citation_battery` (50-q), `test_channels`, `test_agents`, `test_practice`, `test_invoicing`, `test_provisioning`, `test_entitlements`, `test_analyses`, `test_expert_chat`, `test_clearance`, `test_privilege_pentest`, `test_rls`, `test_zdr_filter`, `test_chunker`, `test_ingest_db`, `test_metadata`, `test_internal`, `test_packs`, `test_provider_fallback`, `test_vault_a_ingest`, `test_kyc`, `test_persona`, `test_matters`.

### Frontend — `apps/web/src/`

| File | Responsibility |
|---|---|
| `router.tsx` / `routeTree.gen.ts` / `start.ts` / `server.ts` | TanStack Start bootstrap + generated route tree. |
| `routes/` | `__root.tsx` (root layout + error/not-found), `index.tsx` (marketing home). **Auth boundary (Part 3 S1):** `_authed.tsx` pathless layout guard (no session → redirect `/signin`; bypass when `VITE_API_DEV_ADAPTER=1`) wraps `_authed.search.tsx`, `_authed.tracker.tsx`, `_authed.red-teamer.tsx`, `_authed.workbench.tsx`, `_authed.home.tsx` (→ `/home`, workbench landing for everyone — §8.5), `_authed.firm-command.tsx` (→ `/firm-command`, admin-only run-the-firm surface). Public: `signin.tsx` (password + magic-link), `accept-invite.tsx` (`?token=` sets password → activates seat). |
| `components/AppShell.tsx` | App chrome (navigation + brand); NAV gains admin-only **Firm Command** (`Landmark`) item filtered by `getFirmAdmin()`. |
| `components/ui/*` | shadcn/ui-style primitives (button, card, dialog, tabs, …). |
| `lib/api/client.ts` | Typed `apiPost`/`apiGet` fetch client; forwards Bearer Supabase JWT; `ApiError`; base `http://127.0.0.1:8000`/`VITE_API_BASE_URL`. |
| `lib/api/workbench.ts` | `useAnalyses`/`useAnalysis` → `/v1/analyses`, `Analysis` (wire mirror of AnalysisStatus). |
| `lib/api/firmAdmin.ts` | Firm Command typed client: `useFirmOverview`/`useAdminLedger`/`useFirmSettings` → `/v1/firm/admin/*` (all server-gated by `require_firm_admin`). |
| `lib/api/query.ts`, `deadlines.ts`, `redteam.ts`, `types.ts` (+ `dev/*` adapters) | Other typed API modules + dev adapters. |
| `lib/auth/supabase.ts` | Minimal Supabase Auth HTTP client: `signInWithEmail` (OTP magic link), `verifyOtp`, `signInWithPassword` (Part 3 S1), `getSession`, `getAccessToken`, `getClearance` (decodes JWT `app_metadata.clearance`, fails closed to STAFF), `getFirmAdmin` (decodes JWT `app_metadata.is_firm_admin`, fails closed `false`), `signOut`. |
| `lib/court-filters.ts`, `error-page.ts`, `utils.ts` | Helpers. |
| `styles.css` | Tailwind + brand theme (dark default). |
| `components/marketing/Receptionist.tsx` | **Rennie** — front-desk marketer widget on the marketing home. Deterministic local classifier over `data/receptionist-knowledge.json` (identity → workflow → faq → capability hits → escalate). No network, nothing persisted. Off-corpus always escalates with the exact line. No seeded question pills. |
| `data/receptionist-knowledge.json` | Receptionist corpus: `capabilities` (shipped/roadmap), `faq`, `positioning` (OS line), `workflow` (day-in-the-life Q/A: 5-lawyer firm, adoption, replaces, morning, matter work, intake, billing, where-to-start, about), `plain`. |

### Docs — `docs/`
`master-prompt.md`, `RedCase-Phase1/2/3-Design.md`, `RedCase-Feature-Addendum.md` (§7 comms v2, §9.1 practice ops), `deploy-runbook.md`, `design-system-guidelines.md`, `MVP-Audit-Refactor-Plan.md`, `RC-BrandTheme.md`, `explabs_coding_probe.py`.

7. **Brand** — crimson `#D0021B`, obsidian `#0F1115`, vellum `#E2C044`; dark UI default.
8. **Evidence** — every claimed measurement must be a committed artifact (file path) or it is unmeasured.

---

## [State of Play]

**Branch:** `main` (ahead of origin — NOT pushed).

### Completed
- **OBS — Pragmatic Observability ✅ COMPLETED (committed + pushed `87ddbe8`):** `app/observability.py` (Prometheus registry, counters ANSWER_REFUSALS/ANSWER_TIMEOUTS/FABRICATION_REFUSALS/PROVIDER_FALLBACKS, gauges HEALTH_DB/HEALTH_PROVIDERS); `/v1/metrics` + `/v1/health/detail` added to `main.py`; instrumentation in `retrieval/service.py` (refusal/timeout/fabrication counters) + `retrieval/clients.py` (`FallbackLLM` provider-fallback counter); `prometheus-client>=0.21.1` in `pyproject.toml`; `docs/alert-rules.md` (moved from `apps/api/deploy/` — `.md` gitignored except `docs/**`); `tests/test_observability.py` 7/7. Notes: delta-based counter assertions (counters persist in-process); `_isolated_settings()` (`Settings(_env_file=None)`) keeps tests hermetic vs dev `.env`; counter `_name` strips `_total`; health providers checks real API keys (explabs/mistral/cerebras/groq/deepseek/openrouter/anthropic). **uv lock NOT refreshed** (network blocked) — pyproject updated, CI/next dev regenerates.
- **M1 — Assistant tools consolidation ✅ COMPLETED (committed + pushed `2718d54`):** `expert_chat.py` deprecation docstring; `assistant/service.py` AGENT_SYSTEM advertises + implements 4 drill-down tools (`show_overview`/`show_arguments`/`show_similar_cases`/`show_law`) via `_load_analysis_sections` (RLS-scoped by `created_by`, decodes JSON `output.sections`, honest "no section" refusal — no fabrication) + `_run_tool` dispatch; `tests/test_assistant_tools.py` 7/7 (FakeConn returns dict `{"output": ...}` — asyncpg Record style needs `row["output"]` subscript). Web: `components/assistant/AnalysisSectionCard.tsx` reusable card renderer. NOTE: `service.py` uses CRLF — edits must preserve braces/encoding exactly.
- **H1 — Onboarding wizard ✅ COMPLETED:** new web route `routes/onboarding.tsx` (5-step: Account → Workspace → First matter (skip) → Teammates (skip) → Done); non-destructive, persists prefs to `localStorage` (`redcase.onboarding`), hands off to `/signin` (no public signup/matter-create endpoint — seats provisioned via firm invites); Receptionist/Pricing CTAs already link `/onboarding` (prior session). `routeTree.gen.ts` regenerated via `npm run build` (GREEN). **NOT YET COMMITTED.**
- **Audit remediation (2026-09-22) — H2 encoding sweep ✅:** full-tree cp1252-mojibake sweep of `apps/` (the "known 4 files" bound was the H2 lapse; this is a scan, not a memory bound). **48 replacements, 2 files, ZERO remaining** (`_authed.search.tsx` 43: page title `—`, og:title, year-range labels `2020–2026`, placeholder, citation-guard, comment arrows `→`; `AppShell.tsx` 5: `·` middots). Guard rails created: `.editorconfig` (charset=utf-8, LF, final-newline, per-lang indent) + `.gitattributes` (`* text=auto eol=lf`, utf-8 charset per ext, svg/png/binary) so the corruption class cannot silently re-enter via editor or git.

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
- **IA pass 1 / S10-4 — personnel identity + Home-as-inbox rework (in progress) ✅ backend + frontend core:** backend `app/routers/members.py` (GET `/v1/members/me` → real `full_name`/`role`/`clearance` from `firm_members` + `firm_name` from `tenants`, RLS tenant-scoped; wired in `main.py`); `tests/test_members.py` (4/4 pass, seeds tenant+member via asyncpg, cross-tenant isolation). Frontend `lib/api/members.ts` (`Membership` wire model + `useMembership()` react-query hook, 404→null). `_authed.home.tsx` — eyebrow now shows `{full_name} · {firm_name}` (falls back `{clearance} · redcase`); kept the Workbench hero card; replaced old tool-card grid with a header-less **Home menu** = Time logger (Clock-in/Clock-out local state, attendance=Phase 4 correction §1.2), Partner's Locker → /workbench, Scheduler → /tracker, My matters/My deadlines → /workbench (design doc §2 Home-as-inbox). `AppShell.tsx` — header identity now from `useMembership()` (name · role, fallback clearance) replacing hardcoded "Tosin Adebayo · Managing Partner"; nav label "Case Red-Teamer"→"Red-Teamer". `_authed.red-teamer.tsx` title/meta "Case Red-Teamer"→"Red-Teamer"; `_authed.firm-command.tsx` ADMIN_TOOLS "Case Red-Teamer"→"Red-Teamer". My changed files tsc-clean; pre-existing `AnalysisSectionCard.tsx` exactOptionalPropertyTypes error remains (out of scope). Backend ruff clean + members tests green.
- **S10-4 frontend (access-request flow + analysis chaining) ✅ COMPLETED:** new `lib/api/access.ts` typed client (`AccessRequest` wire model, `useAccessRequests()`, `useCreateAccessRequest()`, `useDecideAccessRequest()`); `lib/api/workbench.ts` adds `chainAnalysis()`/`useChainAnalysis()` (POST `/v1/analyses/{id}/chain`, body `{prompt_pack}`, 202 → child analysis via `parent_analysis_id`, §1.7). `_authed.workbench.tsx` adds a **"Re-analyze with…"** select + Chain button on COMPLETE analyses (offers the OTHER packs, disabled while pending, `GitBranch` icon). `_authed.firm-command.tsx` adds **Access requests panel** (`ShieldCheck`) — lists the caller's requests (awaiting decision for PARTNER/ADMIN deciders), Approve/Deny buttons writing the real `document_grants` ACL, resolves PENDING→APPROVED/DENIED badges. 10 backend tests (access+analyses) pass; `npm run build` GREEN (rolldown).
- **Part 1 — Marketing website (in progress)** — `/` is now the public marketing landing; Vault Search relocated to `/search` (route `search.tsx`, export renamed `SearchPage`); AppShell nav `/`→`/search` (lines 6/55/118). New `src/components/marketing/` = MarketingLayout (sticky nav + footer + Eyebrow), Hero (uses SplitVaultVisual), SplitVault (Vault A/B + Juris 41,902 + skeleton shimmer), Problem, DualVault, Trust, RedTeam (adversarial battle-card artifact), SecureMessenger (chat-thread mock), Workbench (SmartBrief pipeline — renamed from BriefBot), Operations, Security, Pricing, Receptionist (chat panel grounded ONLY on `src/data/receptionist-knowledge.json`; off-corpus → "I don't want to guess — let me connect you." + Talk-to-us; pricing → "Talk to us."; purely local, nothing persisted / no network). **Receptionist converted from full-width `<section>` to a fixed bottom-right floating chat widget** — `Headset` launcher button (z-50, crimson gradient, gold ring, pulsing online dot), collapsible `panel`-styling aside (`surface` + `shadow-elevated`), auto-scroll via ref, suggestion chips, escalate notice, ephemeral no-network footer. Det left `answer()` classifier byte-preserved; added `[price|...]` guard → "Talk to us." and capability/citation encryption fallbacks. Em-dashes written as real UTF-8 (no BOM); tsc-clean for Receptionist; `npm run build` GREEN. Faq.tsx deleted (answers live in the knowledge file). Favicon→`/brand/redcase-mark-crimson.svg`. Brand SVGO-optimized in `apps/web/brand/` + `public/brand/`. `ADVERSARIAL_BRIEF` code constant untouched (display-only rename). Next: commit per repo conventions.
- **Rennie rework (owner direction) ✅ COMPLETED — receptionist = front-desk marketer, not an FAQ robot.** `Receptionist.tsx`: opening message EXACTLY `"Hi, I'm Rennie, RedCase's receptionist. How may I help you today?"`; **all seeded question pills removed** (SUGGESTIONS array + JSX deleted). `receptionist-knowledge.json`: added `positioning` (the OS line, flagged as positioning not a feature claim) + `workflow` array of 9 day-in-the-life Q/A pairs (5-lawyer litigation firm, non-technical adoption + where-to-start Core/Workbench, what-it-replaces, morning = deadline radar + overnight intake + pre-engagement conflict, matter work = matter channel + vault research + Legal Assistant + battle-card opposing brief, intake = conflict check BEFORE engagement letter, billing = in-channel time → one-click invoice, what-is-RedCase). `answer()` classifier order now **identity → workflow → faq → capability hits → escalate** (moved workflow BEFORE faq so "what does it replace?" isn't swallowed by the FAQ word-overlap matcher). **DoD verified:** npm build GREEN; **6 canned probes pass** (3 existing FAQ probes + 3 workflow probes) + identity + off-corpus still escalates with the EXACT line; nothing persisted (still local-only, no network). SHIPPED vs ROADMAP discipline preserved — the OS/workflow framing is positioning only.

- **Part 2 — Onboarding growth surface (public signup + verify + firm invite) ✅ COMPLETED** — `app/onboarding.py` (ROLE_TO_CLEARANCE ladder — ASSOCIATE→STAFF floor; normalize_email; hash_verify_token; new_verify_token); `app/rate_limit.py` (PublicSignupLimiter, per-IP + per-email sliding window); `app/routers/signup.py` (POST `/v1/public/signup` unauthenticated+rate-limited, POST `/v1/public/verify` — constant-time token check, provisions tenant+vault+CORE sub max_seats=3 in one txn w/ RLS, flips ACTIVE, clears token, verify/provision/activate audit rows); `app/routers/invites.py` (POST `/v1/invites` PARTNER/ADMIN-only, seat-gated — 402 DENY_SEAT at capacity w/o increment, atomic seat consume otherwise, ASSOCIATE→STAFF+PARTNER→PARTNER clearance, 'invite'/'invite_denied' audit). Migration `0018_public_signup.py` = firm_signups/signup_audit/firm_invites. `main.py` mounts both routers + `PublicSignupLimiter` app state. `tests/test_signup_invites.py` fully rebuilt (signup + verify + invites classes, **12 tests**), ruff-clean, paths `/v1/public/signup`+`/v1/public/verify`. **TEST RUN (via project venv): full suite `212 passed, 51 skipped, 0 failed`.** Two real bugs found & fixed while running against embedded PG: (1) the DENY verdict previously raised HTTPException INSIDE its transaction → rolled back the `invite_denied` audit row; refactored to commit the DENY audit in its own txn then raise, and re-set the `app.tenant_id` GUC in the credit txn (is_local=true reset it to "" → `""::uuid` cast error). (2) asyncpg is loop-bound — test DB helpers must run all async work in one `asyncio.run()` per connection lifecycle and set the GUC inside a `conn.transaction()` before reading RLS-scoped tables. **ENV CAVEAT:** `pgserver` cannot be installed by global pip (network-restricted) — **use the repo's project venv `apps/api/.venv` which already has it; do NOT reinstall.**
- **Task 3.9 sub-task 3+ (Addendum §9.1):** payments UI + receivables dashboard (frontend remains). Conflict check backend ✅. Trust ledger deferred (Phase 4).
- **Part 2 DoD commit ✅** — committed `25da33e` `fix(onboarding): invite DENY audit rollback + GUC reset; signup/invite suite green (12/12, full 212/0)` (bundled Legal Assistant companion `app/assistant` + migration 0017 + test_assistant.py so `main.py` wiring builds). HANDOFF.md Audit convention now records the **audit-then-raise pattern** (side effects that must survive get their own txn before the error is raised). Pushed to **origin** (all 92 local commits).
- **Part 3 Slice 1 — Auth Boundary ✅ (build green)** — `_authed` pathless layout wraps `/search`,`/red-teamer`,`/tracker`,`/workbench` (routes renamed `_authed.*`, flat routing); beforeLoad guard: no Supabase session → redirect `/signin`, bypass when `VITE_API_DEV_ADAPTER=1`, SSR-safe (client-only localStorage check). New public routes `/signin` (password grant + magic link via `signInWithPassword`/`signInWithEmail`) and `/accept-invite?token=` (validates token → sets password → activates seat; `lib/api/accept-invite.ts` + dev adapter). `lib/auth/supabase.ts` gains `signInWithPassword` + `getClearance()`. `.env.example` documents `VITE_API_DEV_ADAPTER`.
- **Part 3 Slice 1 backend close — POST /v1/invites/accept ✅ (suite green 216/51)** — migration `0019_invite_accept.py` adds `invite_token_hash` (UNIQUE) / `invite_token_expires_at` / `accepted_at` / `accepted_user_ref` / `accepted_clearance` to `firm_invites`, plus a **SECURITY DEFINER** `redcase_claim_invite(token_hash, now)` that atomically flips a PENDING invite → ACCEPTED (single-use enforced in SQL with `status='PENDING'`; lookup bypasses RLS so the unauthenticated path can learn the tenant from a token — no tenant JWT exists here). `app/onboarding.py` gains `new_invite_token`/`hash_invite_token` (separate subkey namespace). `rate_limit.py` gains `InviteAcceptLimiter` (per-IP + per-token), wired in `main.py`; config gains `invite_accept_rate_*` + `invite_token_ttl_s` (7d). `create_invite` now generates a token and returns it (raw) in the 201 body for the invite link. `accept_invite`: rate-limited, uniform 400 on unknown/used/expired; clearance derived **server-side** from the invite role mapping (client `clearance` field ignored — fail-closed); Supabase Admin API (`/auth/v1/admin/users`) sets `app_metadata {tenant_id, clearance}`; on user-creation failure the invite is re-opened (PENDING); audit `invite_accepted` row written (token hash, email, clearance, tenant). Tests: `TestInviteAccept` (4 tests) — happy path + single-use + expired + clearance-injection-ignored; exercises Supabase via monkeypatch (no service role in CI). **ZDR note (intentional, spec-mandated):** the `invite_accepted` audit `detail` includes the invited email — a documented exception to the "no PII in audit" convention.
- **Part 3 Slice 2 — Role landing by clearance ✅ (build green)** — new authenticated home route `_authed.home.tsx` (→ `/home`, child of the `_authed` auth-boundary layout). `getClearance()` (JWT `app_metadata.clearance`) dispatches fail-closed: **PARTNER/ADMIN → Firm Dashboard** (fast-follow compose of existing typed clients only: `useDeadlineEvents` stat row + upcoming list, `useAnalyses` recent list, quick-link tiles into /search /red-teamer /tracker /workbench); **SENIOR/ASSOCIATE/STAFF → Practitioner Landing** (workbench CTA hero, recent analyses, quick links). `signin.tsx` post-auth redirect `/search` → `/home`; AppShell NAV gains a `Home` entry. No new endpoint invented — composes deadlines + analyses only. `routeTree.gen.ts` regenerated (`/_authed/home`, path `/home`); `tsc` clean for the new file (pre-existing unrelated errors remain in `_authed.workbench.tsx`, `accept-invite.tsx`, `dev/accept-invite.ts`, `MarketingLayout.tsx` from the earlier uncommitted web work); **`npm run build` GREEN (✓ built)**. Added runbook note `docs/deploy-runbook.md` "privileged operations that cannot carry a session" (three patterns: per-txn GUC, SECURITY DEFINER token claim, fail-closed). Earlier Slice-1 approver guidance: the email-in-audit deviation is acceptable; backlog refinement = store email hash + resolved user_ref instead of raw email (deferred).**Next:** coach marks, then ONE push of `main` completes Part 3.

- **Part 3 Slice 3 - Coach marks + cleanup (tsc clean, build green, PUSHED):** new shared `apps/web/src/components/CoachMarks.tsx` (dismissible 3-step overlay spotlighting search / workbench / home dashboard; keyed to `redcase.coach.<user_ref>.<surface>` in localStorage - never server-persisted, never re-nags). Wired into `_authed.home.tsx`, `_authed.search.tsx`, `_authed.workbench.tsx`. Cleanup fixed all 4 pre-existing TS error files: `_authed.workbench.tsx` (`Record<string,any>` to `any` for freeform AI output - `noPropertyAccessFromIndexSignature` blocks index-signature dot-access), `dev/accept-invite.ts` (circular import), `accept-invite.tsx` (`exactOptionalPropertyTypes` + TS4111 bracket access), `MarketingLayout.tsx`/`Hero.tsx`/`index.tsx` (`/onboarding` to `/signin`, dead route from web migration). `tsc` CLEAN (0 errors), `npm run build` GREEN. API suite unchanged (web-only task). **Drift committed + pushed to origin in ONE push of main (`5822336..a12f14b`)** via 4 focused commits: `f127387` (authed-surface rework under `_authed` layout + supabase password/clearance + .env adapter flag), `640967c` (invite-accept flow: public route + typed client + dev adapter), `9104d7e` (marketing cleanup: /signin CTAs + FAQ nav drop + design-doc encoding), `a12f14b` (coach marks Slice 3). **PART 3 web slices COMPLETE** - only 3.3-3.8 backend/feature phases remain.

- **H3 Firm Command (admin-only surface) ✅ backend + frontend — Addendum §8.5** — Implemented item (1) of the H3 admin surface model:
  - **Backend:** migration `0020_firm_admins.py` (append-only `firm_admins` ledger, tenant-scoped RLS, seeds managing partner `mp-aetoes`); `TenantContext.is_firm_admin` + `require_firm_admin` dep in `deps.py` (reads JWT `app_metadata.is_firm_admin`, fails closed `False`, 403 for non-admins even at PARTNER — orthogonal to clearance). `routers/firm_admin.py` (overview/seats, invites, transparency feed re-export, admin ledger, admin grants POST, firm settings) wired in `main.py`. Append-only DB grant enforced in `conftest.py`. `tests/test_firm_admin.py` (5/5 pass).
  - **Frontend:** `lib/api/firmAdmin.ts` typed client (useFirmOverview/useAdminLedger/useFirmSettings); `getFirmAdmin()` in `supabase.ts` (decodes JWT `app_metadata.is_firm_admin`). New route `_authed.firm-command.tsx` (`/firm-command`, child of auth boundary) — seats stats, approve admin-grant ledger, firm settings, upcoming deadlines (`useDeadlineEvents`), recent analyses (`useAnalyses`), tool tiles. `_authed.home.tsx` now dispatches EVERYONE to `PractitionerLanding` (removed PARTNER→FirmDashboard redirect; kept AnalysisStatus/PACK_LABEL). `AppShell.tsx` renames Home nav sub to \"Workbench landing\" and adds admin-only **Firm Command** nav item (`Landmark` icon) filtered by `getFirmAdmin()`. `routeTree.gen.ts` regenerated (path `/firm-command`); `tsc` clean, `npm run build` GREEN (exit 0).

- **Phase 3 remaining:** 3.3 battle-card rendering, 3.4 deadline rule pack (`deadlines/` module NOT YET created), 3.5 notification fan-out, 3.6 observability/Langfuse, 3.7 benchmark+calibration, 3.8 training/go-live.
- **Backlog:** Slack connector (post-deploy), deadline sweeps, reranker (deferred with evidence).
- **Cloudflare cron worker (Task 1.7 step 5, deployed 2026-09-23):** worker `redcase-cron`
  deployed to owner account `e9f3f471…` → `https://redcase-cron.affos.workers.dev`.
  Config in `cloudflare/` (commits `4380af8`, `8bbdbb9`). **Single** cron `*/5 * * * *`
  due to free-plan 5-trigger limit (4 already used by affiliateos/pathguru); worker gates
  daily 06:00 UTC sweep internally + health keep-alive each tick. `API_BASE_URL` var =
  `https://api.redcase.xyz`; secret `INTERNAL_SWEEP_TOKEN` sent as `X-Internal-Token` header.
  Verification status: API now LIVE via VPS manual deploy (2026-09-23, see below); sweep still needs owner-set
  `INTERNAL_SWEEP_TOKEN` matching `/opt/redcase/.env` + `SUPABASE_JWT_SECRET`. Details in `docs/deploy-runbook.md` §3a.
- **✅ FIRST MANUAL DEPLOY to VPS (2026-09-23) — api.redcase.xyz 502 RESOLVED.**
  - **Host:** owner VPS via `ssh redcase-vps` (Cloudflare-tunneled; key `redcase_deploy`; ssh host alias uses
    `cloudflared` ProxyCommand `C:\Program Files (x86)\cloudflared\cloudflared.exe`).
  - **Deploy method:** image BUILT ON-BOX. Repo cloned to `/opt/redcase/src` (public). `docker-compose.yml`
    in `/opt/redcase` uses `build: context /opt/redcase/src, dockerfile apps/api/Dockerfile`, `127.0.0.1:8000:8080`
    (app listens on 8080 per Dockerfile CMD — NOT 8000), `env_file /opt/redcase/.env`, `restart: unless-stopped`,
    healthcheck on `http://localhost:8080/v1/health`. Container `redcase-api` **Up (healthy)**.
  - **Migrations:** ran FIRST from laptop venv `apps/api/.venv` against the LIVE Supabase project
    (`alembic upgrade head`), 0010→0020, confirmed `alembic_version = 0020 (head)`.
  - **DEFECT FIXED (first-deploy catch):** migration `0019_invite_accept.py` did unguarded
    `GRANT ... TO redcase_app` but that role EXISTS ONLY in test fixtures (created by conftest.py), not the live
    Supabase project → transaction rolled back (DB stayed at 0010). Fixed by wrapping the GRANT in a `DO $do$ ...
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='redcase_app')` guard. **Also synced the fixed 0019 + regenerated
    `uv.lock` (0019 was missing prometheus-client → `uv sync --locked` failed the docker build) to the VPS clone.**
  - **Verified live:** `GET /v1/health` → 200 `{"status":"ok"}`; `GET /v1/metrics` → Prometheus exposition;
    locally-bound `/v1/query` enforces auth (401 missing Bearer).
  - **STILL BLOCKED (step 5c):** real `/v1/query` grounded answer needs `SUPABASE_JWT_SECRET` in `/opt/redcase/.env`
    (owner-held; absent from both local `.env` and VPS `.env` + container env). Without it `get_tenant_context` 503s.
    Owner must add `SUPABASE_JWT_SECRET` (+ signed JWT for aetoes tenant) then `docker compose restart api`.
  - **✅ RESOLVED 2026-09-23 + PAT SMOKE RUN — API FULLY LIVE.** `SUPABASE_JWT_SECRET` + `INTERNAL_SWEEP_TOKEN`
    provisioned in `/opt/redcase/.env`; container recreated with `docker compose up -d` (re-read env_file) → container
    now carries the secret (89 chars). **PAT smoke against `https://api.redcase.xyz`:**
    - Minted smoke JWT on the VPS (stdlib hmac HS256, mirroring `deps.verify_supabase_jwt`; pyjwt not installed in
      any local venv — used stdlib instead, same crypto). `sub=smoke-test`, `app_metadata.tenant_id=a0000001-...0001`
      `clearance=PARTNER`, `is_firm_admin=true`.
    - Answer path (Amaechi v. INEC) → **200, refusal:false, 1 verified citation** (page 8, ¶[1,2], verified:true),
      **zero fabrication → PASS**.
    - Out-of-corpus (interim-injunction) → **UNDER-REFUSAL: answered** (2 verified citations, no fabrication) — **the
      B17 under-refusal guard FAILS on live**; zero-fabrication gate holds.
    - Cron cascade: `GET /v1/health 200` keep-alive rows in logs; `POST /v1/internal/sweep` (X-Internal-Token) →
      **200 `{"pending":0,"embedded":0}`** + `sweep_done` audit event.
    - **Latency on live VPS (Madukolu, n=10): p50=39.8s p95=41.6s max=41.7s, 6/10 over 20s ceiling →
      BOTH BARS FAIL.** Root cause (logs): `ANSWER_MODEL_PRIMARY=deepseek` + `openrouter` + `cerebras` all
      **quota_exhausted** on live → every answer burns the 20s timeout, resolves only via the funded Groq leaf; 6/10 became
      double-timeout refusals. Recorded verbatim in `docs/calibration/phase1-jina.md` "Live VPS (Johannesburg)"; bars NOT
      amended. Grounding/fabrication gates held throughout.
  - **Pipeline still pending the CI fix:** the on-box build + manual migrations substitute for `deploy.yml`; the CI/deploy
    workflow + GCP/CI secrets not yet provisioned (owner). Commit status: `0019` + `uv.lock` fixes are UNCOMMITTED working-tree
    changes on the laptop — must be pushed to `main` so the pipeline picks them up.

- **Blocker:** Phase 1 deploy held pending owner credentials (CI secrets, GCP SA, CF zone).

### Working-tree notes
- `MEMORY_BANK.md` + `.gitignore` negation committed (`4dc9bb4`); the `.md` ignore now exempts MEMORY_BANK.md so future commits need no force-add.

### Session S10 progress (2026-09-23)
- **SLICE 0 (S10-0) — sign-in bug sweep + PRODUCTS band ✅ COMPLETED:**
  - `routes/signin.tsx`: "Back to redcase.ai" → `redcase.xyz`; logo `<img>` → `/brand/redcase_firefly.svg` (copied from `docs/RedCaseSVG/`, `h-10 w-auto object-contain`, not stretched); added "New firm? Start your firm →" link → `/onboarding`; bottom mark → `/brand/redcase-mark-white.svg`.
  - `routes/accept-invite.tsx`: logo → firefly (same sizing); "Back to redcase.ai" → `redcase.xyz` (same bug class).
  - `routes/__root.tsx`: favicon → `/brand/redcase-mark-favicon.svg` (was `redcase-mark-crimson.svg`).
  - Landing `routes/index.tsx` + new `components/marketing/Products.tsx`: **PRODUCTS band** between DualVault and Trust — eyebrow "THE PRODUCT", H2 "Four surfaces. One engine.", 4 preview cards (Vault Search / Red-Teamer / Legal Assistant / Firm Ops).
  - `apps/web/public/brand/redcase_firefly.svg` = byte-identical copy of `docs/RedCaseSVG/redcase_firefly.svg` (hash A94AF47…; 754,908 B).
  - **DoD verified:** `npm run build` GREEN (only pre-existing rolldown "use client" directive warnings). No `redcase.ai` refs remain in web routes; `onboarding.tsx` crimson logo pending full rewrite in SLICE 1.
- **SLICE 1 (S10-1) — firm identity + KYC funnel ✅ COMPLETED (2026-09-23):**
  - **Migration `0021_firm_kyc.py`:** `tenants.logo_path` column; new `firm_kyc` table (id, tenant_id UNIQUE, cac_number, rc_document_path, admin_id_type, admin_id_document_path, firm_website, verification_status CHECK PENDING/VERIFIED/REJECTED DEFAULT PENDING, submitted_at, reviewed_by, reviewed_at) with tenant-scoped RLS policy + firm-admin gate (reads `app.is_firm_admin` GUC, PARTNER_RESTRICTED-analog); `id_document_type` added (spec guards NIN/DRIVER_LICENSE/INTL_PASSPORT). `redcase_app` GRANTs in idempotent `pg_roles` guard (pattern from 0019). Storage **paths only** — bytes never stored; KYC doc class = PARTNER_RESTRICTED.
  - **`config.py`:** added `storage_kyc_bucket="firm-kyc"`, `storage_kyc_prefix="kyc"`.
  - **`app/routers/kyc.py`** (new, mounted in `main.py`): `GET /v1/firm/kyc` (returns row or 404) + `POST /v1/firm/kyc` (upsert; requires BOTH rc_path + id_document_path → 422 otherwise; resets `verification_status` to PENDING on every submit; no client path to VERIFIED/REJECTED — ops-only for tenant zero); both gated by `deps.require_firm_admin` (orthogonal `is_firm_admin` JWT flag, fail-closed). ZDR-clean (paths + status only).
  - **`tests/test_kyc.py`** (new, 5 tests GREEN): non-admin 403 (incl. PARTNER w/o flag), both-docs-required 422, submit+read-back PENDING, tenant-RLS 404 for another tenant's admin, upsert resets PENDING after ops VERIFIED.
  - **`onboarding.tsx`** (rewritten): wizard now 6 steps — Account → **Firm identity** (firm name, logo path preview + storage-path input, juris→practice, website) → **KYC** (RC path, admin ID path, ID document type select, website) → First matter → Teammates → Done. Logo shows in the wizard header; KYC captures storage **paths only** (no upload in this slice). Handoff to `/signin`.
  - **DoD:** `pytest tests/test_kyc.py` = 5/5 GREEN; `npm run build` GREEN (only pre-existing rolldown "use client" warnings); `docs/RedCase-Feature-Addendum-S10.md` §10.6 S10-1 marked ✅ DONE.
- **SLICE 2 (S10-2) — agent persona (per-user agent_name, rules_of_engagement, tone_preset) w/ practice-area lens ✅ COMPLETED (2026-09-23):**
  - **Migration `0022_practice_areas_personas.py`:** new `practice_areas` + `user_personas` tables; practice-area lens = `legal_topics && $10` array-overlap pre-filter in BOTH vector + FTS branches of HYBRID_SQL. Verified via alembic upgrade head fixture. `_show_similar_cases` NOT filtered by practice areas (stored analysis sections already scoped).
  - **`app/routers/persona.py`:** `GET /v1/persona` (open), `PUT /v1/persona` (firm-admin gated), `GET/PUT /v1/persona/practice-areas` — PUT returns SORTED tags (consistent with GET). Persona injected as `{persona}` AFTER grounding rules — GROUNDED_SYSTEM contract survives byte-for-byte.
  - **`tests/test_persona.py`** (rewritten from scratch): 11 tests GREEN. **`test_assistant.py`:** `fetchrow`→None added to both `_FakeDB` classes (needed by `_fetch_persona` in `run_assistant_turn`). Full suite 251 tests pass.
  - **Frontend:** `lib/api/client.ts` — `apiPut<TResponse, TRequest>`. `lib/api/persona.ts` (new) — types (Persona/PersonaInput/TonePreset/PERSONA_TONES) + hooks (usePersona/usePracticeAreas/useSavePersona).
  - **Onboarding (`routes/onboarding.tsx`):** Assistant step at index 4 (0 Account, 1 Firm, 2 KYC, 3 Matter, **4 Assistant**, 5 Teammates, 6 Done). FormState gained agentName/tone/rules/practiceTags; StepAssistant form (name, tone select, rules textarea, practice tags comma-input); finish() persists via savePersona (try/catch, non-fatal).
- **SLICE 0 identity fallback (S10-0 continuation) — IMPLEMENTED, build verified (2026-09-24):**
  - `apps/web/src/lib/identity.ts`: centralized display identity chain: membership full name → capitalized JWT email local-part → `Counsel`; no `ANON` rendering. Provides firm/role/clearance metadata and header eyebrow.
  - `apps/web/src/lib/api/members.ts` + `lib/api/dev/members.ts`: typed `/v1/members/me` client with explicit `VITE_API_DEV_ADAPTER=1` persona (`Tosin Adebayo`, `Managing Partner`, `Aetoes Legal`, `PARTNER`) for offline/demo verification.
  - `apps/web/src/lib/auth/supabase.ts`: decodes the JWT email claim for the fallback chain.
  - `components/AppShell.tsx` and `routes/_authed.home.tsx`: use `useIdentity()` for the header chip and Home greeting, including initials.
  - `npm run build` completed successfully. Repository-wide `npm run lint` remains blocked by pre-existing CRLF/Prettier normalization noise (2,902 errors across the frontend); no mass reformat was applied.
  - Visual verification completed (2026-09-24): after waiting for the async membership query to settle in the adapter-enabled dev server, Home renders `Welcome, Tosin Adebayo`, eyebrow `TOSIN ADEBAYO · MANAGING PARTNER · AETOES LEGAL`, and the `TO` initials chip. Final capture: `slice0-home-final.png`. Earlier `Counsel`/`CO` observations were the pre-query SSR/loading state, not a runtime identity defect.
- **UX-1 shell restructure — IMPLEMENTED and build-verified (2026-09-24):** `components/AppShell.tsx` now follows the cockpit shell direction: compact icon rail, contextual sub-panel for Home/Workbench/Vault/Messenger/Tracker/Firm Ops, admin-only Firm Ops visibility, header search/notifications/help affordances, identity chip, mobile route strip, and bottom task bar with local density toggle. Existing routes remain the only navigable destinations; unavailable Messenger sub-items are visibly disabled rather than backed by invented endpoints. `npm run build` passes; repository CRLF normalization warnings remain as previously documented.
- **UX-2 onboarding services + departments — IMPLEMENTED and build-verified (2026-09-24):** added migration `0024_tenant_departments.py` with tenant-scoped/RLS-protected department selections; extended `app/routers/persona.py` with admin-gated `PUT /v1/persona/departments` (always retains locked `Legal Practice`) and tenant-readable GET; added typed frontend persistence in `lib/api/persona.ts`; onboarding now has a dedicated Services & departments step with accessible toggle cards for the ten specified services and four department modules, with the Zoho reassurance copy and locked Legal Practice state. Finish persists services, departments, and the existing assistant persona. `npm run build` passes; targeted Python compile and `git diff --check` pass, with only known CRLF normalization warnings.
- **UX-3 Home-as-inbox + task bar — IMPLEMENTED and build-verified (2026-09-24):** Home now seeds four explicit widgets—Inbox, Today, My deadlines, and My matters—using the existing analyses and deadline-event clients with loading, empty, and error states; deadline rows are tenant-scoped through the existing API contract and link to the real Tracker/Workbench surfaces. AppShell's bottom task bar now exposes Pins, Chats, Channels, Threads, and Contacts with real routes and live backend contracts.
- **UX-3 collaboration completion — IMPLEMENTED and build-verified (2026-09-24):** Added `0025_collaboration_workspace.py` as a merge migration for the two existing 0024 heads, creating tenant/user-RLS `user_pins` reference records. Added `app/routers/collaboration.py` for pins, firm member directory, and validated reference ownership; extended assistant API with owner-scoped thread listing. Added typed web clients and `CollaborationWorkspace` with responsive Pins, Chats, Channels, Threads, and Contacts surfaces; channels support real message read/send, pins support create/delete, and assistant threads have a real detail route with SSE send/recovery. New routes are `_authed.pins/chats/channels/threads/contacts.tsx` plus `_authed.threads.$threadId.tsx`; AppShell task-bar items are links rather than disabled labels. `npm run build`, Python `compileall`, and `git diff --check` pass. Full API integration tests require the repository's provisioned Python dependencies/database; existing unrelated generated/design artifacts remain untracked and untouched.
- **SLICE 3 (S10-3) — matter assignment + Firm Command progress panel ✅ COMPLETED (2026-09-23):**
  - **Migration `0023_matter_assignment.py`:** `matters.assigned_to TEXT` + `matters.progress_note TEXT`; index `matters_assigned_idx (tenant_id, assigned_to)`; recreated `tenant_isolation` ON matters WITH **WITH CHECK** (0008's USING-only policy blocked app-role UPDATE — WITH CHECK is what lets the non-owner app role write through RLS). Verified: full `alembic upgrade head` chain 0001→0023 applies clean (the `0023` probe: `ADD COLUMN x, ADD COLUMN y` — stacked `ADD COLUMN … ADD COLUMN` is a PG SYNTAX ERROR). downgrade drops idx/policy/columns.
  - **`app/routers/matters.py`:** `POST /v1/matters/{id}/assign` (PARTNER/ADMIN clearance OR firm-admin; assignee must be a licensed firm user — ACCEPTED firm_invite — else 422; matter tenancy validated via `_get_matter` since the FK bypasses RLS), `GET /v1/matters/{id}`, `GET /v1/matters/my` (`assigned_to = me`), `GET /v1/firm/matters/progress` (firm-admin-gated panel composing EXISTING data: `analyses_count` + `time_minutes` subqueries). Wired into `main.py`.
  - **`tests/test_matters.py`** (new, 7 tests GREEN): PARTNER+admin assigns (progress_note persisted); staffer w/o admin 403; made-up assignee 422; unknown/cross-tenant matter 404; `/my` returns only assigned; progress panel 403 for non-admin, 200 + composed counts (2 analyses, 55 min).
  - **DoD:** `pytest tests/test_matters.py` = 7/7 GREEN; ruff clean on matters.py + test_matters.py + 0023.
  - **Workbench (`routes/_authed.workbench.tsx`):** `PersonaSettings` panel under the container — loads usePersona/usePracticeAreas (useEffect populate), saves via useSavePersona.mutate, success/error flash. Discoverable on Workbench page.
  - **DoD:** `npx tsc --noEmit` — persona/onboarding/workbench files CLEAN; `npm run build` GREEN (only pre-existing rolldown "use client" warnings + pre-existing AnalysisSectionCard tsc error outside S10-2 scope). 251 backend tests pass (incl. 11 persona).



---

## [Operational Notes]
- **Frontend:** TanStack Start (NOT Next.js — deviated, recorded).
- **Backend:** FastAPI, async/await, asyncpg, raw SQL (no ORM); migrations via Alembic-style `op.execute`.
- **Quality gates:** ruff clean; `pytest` in `apps/api`.
- **Env:** Windows/PowerShell — `&&` does NOT work; use `;` or separate commands.
- **Update rule:** after modifying files, running tests, or changing schema, update this file immediately.
- **Drift caveat:** Uncommitted/untracked drift is not reflected here; run `git status` before assuming the map is complete.

