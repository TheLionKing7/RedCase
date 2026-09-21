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
    DENY_SUSPENDED→403. Premium set = {workbench.analyze, workbench.chat}.
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
| `internal.py` | Internal/sweep endpoints | Token-gated. |
| `audit.py` | Audit read endpoints | |
| `vault_a.py` | Vault A routes | Clearance-gated ingestion/retrieval. |
| `practice.py` | `POST/GET /v1/matters/{matter_id}/time` | Time capture (3.9 sub-task 1). `ops.time` CORE entitlement; matter tenancy validated; idempotency on (tenant_id, idempotency_key); minutes>0; returns total_minutes. |
| `invoicing.py` | `POST /v1/matters/{id}/invoice`, `GET /v1/matters/{id}/invoices`, `GET/POST /v1/invoices/{id}`, `POST /v1/invoices/{id}/send`, `GET /v1/invoices/{id}.pdf`, `POST /v1/invoices/{id}/payments`, `GET /v1/receivables/aging` | Invoicing + payments (3.9 sub-task 2). `ops.invoicing` premium gate; per-tenant `RC-<N>` numbering; line amount = minutes/60 × hourly rate_ngn; DRAFT→SENT (send, `sent_at`), payment → PARTIAL/PAID; PDF via `app.invoicing_pdf` (pymupdf, brand letterhead); aging buckets for receivables. |
| `_load_invoice` helper | (in invoicing.py) | Fetches invoice + `paid_ngn`/`balance_ngn` + optional lines; 404 on foreign/unknown. |


### Migrations — `infra/supabase/migrations/versions/`

Sequential `0001`…`0015`:
`0001_phase1_core`, `0002_query_audit_rls`, `0003_workbench_tables`, `0004_entitlements`, `0005_channels`, `0006_embedding_2048`, `0007_embedding_1024_jina`, `0008_vault_a_clearance`, `0009_clearance_ladder`, `0010_provider_provenance`, `0011_channels_v2`, `0012_agent_participation`, `0013_expert_chat_thread`, `0014_time_entries`, `0015_invoicing`.
- `0014_time_entries.py`: `time_entries` (tenant_id, matter_id FK→matters, user_ref, description, minutes>0, rate_ngn, billed, idempotency_key, created_at, worked_at) + (tenant_id, matter_id) idx + unique (tenant_id, idempotency_key) idx + RLS tenant_isolation.
- `0015_invoicing.py`: `invoices` (tenant_id, matter_id, number, status DRAFT/SENT/PARTIAL/PAID, amount_ngn, due_date, sent_at, created_at) + `invoice_line_items` (snapshot of each billed entry) + `payments` (invoice_id, amount_ngn, method, received_at) + RLS on all three. Per-tenant `RC-<N>` invoice number sequence.

### Tests — `apps/api/tests/` (pytest)

`conftest.py` (fixtures/app factory), `pdf_factory.py`, plus `test_app`, `test_query_api`, `test_router`, `test_retrieval`, `test_citation_battery` (50-q), `test_channels`, `test_agents`, `test_practice`, `test_invoicing`, `test_provisioning`, `test_entitlements`, `test_analyses`, `test_expert_chat`, `test_clearance`, `test_privilege_pentest`, `test_rls`, `test_zdr_filter`, `test_chunker`, `test_ingest_db`, `test_metadata`, `test_internal`, `test_packs`, `test_provider_fallback`, `test_vault_a_ingest`.

### Frontend — `apps/web/src/`

| File | Responsibility |
|---|---|
| `router.tsx` / `routeTree.gen.ts` / `start.ts` / `server.ts` | TanStack Start bootstrap + generated route tree. |
| `routes/` | `__root.tsx` (layout), `index.tsx` (dashboard), `workbench.tsx` (tabbed Summary/Arguments/Similar/Law), `tracker.tsx`, `red-teamer.tsx`. |
| `components/AppShell.tsx` | App chrome (navigation + brand). |
| `components/ui/*` | shadcn/ui-style primitives (button, card, dialog, tabs, …). |
| `lib/api/client.ts` | Typed `apiPost`/`apiGet` fetch client; forwards Bearer Supabase JWT; `ApiError`; base `http://127.0.0.1:8000`/`VITE_API_BASE_URL`. |
| `lib/api/workbench.ts` | `useAnalyses`/`useAnalysis` → `/v1/analyses`, `Analysis` (wire mirror of AnalysisStatus). |
| `lib/api/query.ts`, `deadlines.ts`, `redteam.ts`, `types.ts` (+ `dev/*` adapters) | Other typed API modules + dev adapters. |
| `lib/auth/supabase.ts` | `getAccessToken`. |
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

### In Progress / Next
- **Task 3.9 sub-task 3+ (Addendum §9.1):** payments UI + receivables dashboard (frontend), **AI conflict check at client intake** (party names vs. Vault A + matters + corpus). Trust ledger deferred (Phase 4). DoD: time→invoice→payment round-trip test ✅; conflict-check flags planted fixture; synthetic data only.
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

