# RedCase — Implementation Handoff for Kimi Code

**Read order (source of truth):**
1. This file — execution plan, conventions, gates
2. `docs/master-prompt.md` — governing product/architecture constraints
3. `docs/RedCase-Phase1-Design.md` → Phase 2 → Phase 3 — detailed schemas, code, checklists

**Rule: implement phases strictly in order.** Each phase has a Definition of Done (DoD) gate. Do not start Phase N+1 until Phase N's gate passes. Cross-phase shortcuts are how privilege bugs and fabricated citations ship.

**Client context:** Aetoes Legal, 3-partner Nigerian litigation firm. Aetoes is `tenant zero` of a multi-tenant SaaS. All schema is tenant-scoped from day one; only one tenant is provisioned.

---

## 1. Repository Layout (monorepo)

```
RedCase/
├── HANDOFF.md                    ← you are here
├── docs/                         ← design documents (source of truth)
├── apps/
│   ├── web/                      # Next.js 14+ (App Router), TypeScript, Tailwind
│   │   └── brand/                # RedCase SVGs (SVGO-optimize before use; strip
│   │                             #   #EFEFEF bg rect from 16x16.svg)
│   └── api/                      # Python 3.12, FastAPI, uv-managed
│       ├── app/
│       │   ├── main.py           # app factory; mounts /v1/* and /v1/slack/*
│       │   ├── config.py         # pydantic-settings; NO secrets in code
│       │   ├── deps.py           # auth, tenant + user context resolution
│       │   ├── middleware/
│       │   │   ├── zdr.py        # ZDR enforcement + log redaction (Phase 1 §1.3)
│       │   │   └── audit.py      # audit writer → query_audit
│       │   ├── retrieval/        # hybrid search, rerank, gates (Phases 1,3)
│       │   ├── router/           # intent router + dual-vault synthesis (Phase 2)
│       │   ├── redteam/          # 4-agent battle-card engine (Phase 3)
│       │   ├── deadlines/        # rule pack, detection, notify (Phase 3)
│       │   ├── crypto/           # DEK generation, KMS wrap, AES-256-GCM
│       │   ├── slack/            # Bolt app, listeners, intake, render
│       │   └── routers/          # /v1/query, /v1/matters, /v1/documents…
│       ├── scripts/
│       │   ├── ingest.py         # Phase 1 §4 (extend for Vault A in Phase 2)
│       │   └── zdr_audit_check.py
│       └── tests/                # pytest; see §5 testing contract
├── infra/
│   ├── supabase/migrations/      # Alembic-managed DDL from design docs
│   └── docker/                   # api.Dockerfile, worker.Dockerfile
└── .github/workflows/            # CI: lint → test → migrate-check → deploy
```

## 2. Global Conventions (non-negotiable in every phase)

1. **ZDR:** no raw document text, prompt bodies, or LLM request payloads in any log or table. Structlog redaction filter mandatory. Only metadata + generated outputs + citation objects persist.
2. **RLS:** every query executes with `app.tenant_id`, `app.user_ref`, `app.user_clearance` set via `SET LOCAL` on the request's connection. Retrieval filters live in SQL policies, never only in Python.
3. **Audit:** every query, upload, Slack event → `query_audit`. DB role has UPDATE/DELETE revoked. Audit write failure = halt LLM responses.
4. **Citations:** every generated legal proposition carries page/paragraph-pinned citations verified against the retrieved set. Fabricated citation = regenerate once, then refuse/downgrade. Never render unverified citations.
5. **Multi-tenant:** `tenant_id` on every table; no cross-tenant joins without explicit shared-vault flag (`vaults.is_shared`).
6. **Brand:** crimson `#D0021B`, obsidian `#0F1115`, vellum `#E2C044`; dark UI as default theme.

## 3. Environment & Secrets Registry

| Secret / var | Where | Phase |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE` | AWS Secrets Manager | 1 |
| `ANTHROPIC_API_KEY` (ZDR workspace) | Secrets Manager | 1 |
| `OPENAI_API_KEY` (embeddings, via ZDR proxy) or self-hosted embedder | Secrets Manager | 1 |
| `EMBED_MODEL` (`text-embedding-3-large`), `VECTOR_GATE=0.78` | env config | 1 |
| `HMAC_KEY` (content hashes), KMS key ARN for DEK wrapping | Secrets Manager / KMS | 2 |
| `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET` | Secrets Manager | 2 |
| `COHERE_API_KEY` (or `RERANKER=bge_local`) | Secrets Manager | 3 |
| Google/Outlook OAuth client creds (calendar) | Secrets Manager | 3 |
| `LANGFUSE_*` (self-hosted keys) | env config | 3 |

## 4. Phase Execution Plan

### Phase 1 — Vault B Core (target: 10 working days)

| # | Task | Reference | DoD |
|---|---|---|---|
| 1.1 | Scaffold monorepo, CI, FastAPI app factory, config, structlog+ZDR filter | §1 repo, §2 conv | `pytest` green; ZDR filter unit-tested |
| 1.2 | Run Phase 1 §2.1 DDL via Alembic; enable RLS; seed tenant `aetoes` | Phase1 §2.1 | Migration applies clean on fresh DB; RLS policy test passes |
| 1.3 | Ingestion script (page-tracked chunker, metadata extraction, embed+upsert) | Phase1 §4 | 10 benchmark SC PDFs ingested; page/paragraph pins spot-checked correct on 3 docs |
| 1.4 | Hybrid retrieval SQL + `/v1/query` endpoint + threshold refusal | Phase1 §3 | Out-of-corpus test refuses; filtered query respects filters |
| 1.5 | Citation verification + audit persistence | Phase1 §3.4 | 50-question battery: 0 fabricated citations |
| 1.6 | Next.js Vault Search UI (dual-vault selector, filters, pinned-citation cards) | Ops Hub screenshots in docs/ | Renders Phase 1 API end-to-end |
| 1.7 | Deploy: Vercel + Fargate + Supabase; ZDR verification script run | Phase1 §5 | PAT: grounded query cites correct page; refusal correct; p95 < 8s |

**Gate G1:** Phase 1 §5.3 acceptance table fully green.

### Phase 2 — Vault A + Slack Hub (target: 15 working days)

| # | Task | Reference | DoD |
|---|---|---|---|
| 2.1 | `clients`, `matters`, `document_grants`, clearance RLS policies | Phase2 §1.2 | Staff user SQL test: 0 rows on PARTNER_RESTRICTED docs |
| 2.2 | Envelope crypto: DEK gen, KMS wrap, AES-256-GCM field encryption, decrypt-on-retrieve | Phase2 §1.2 | CONFIDENTIAL doc: plaintext absent from DB dump; retrieval decrypts correctly |
| 2.3 | Vault A ingestion path (classification, hash idempotency, grants) | Phase2 §3.5 | PDF → Vault A under matter; re-ingest is no-op |
| 2.4 | Query router (Haiku classify → A/B/BOTH) + dual-vault synthesis with namespace citations | Phase2 §2 | 60-question labeled set ≥90% route accuracy; namespaces never mixed |
| 2.5 | Slack app: mention handler, identity resolution, threaded answers | Phase2 §3.2–3.3 | Mention in #case-* channel returns grounded answer with source buttons |
| 2.6 | `/troubleshoot` loop + attachment intake (`slack_intake` idempotency) | Phase2 §3.4–3.5 | Full loop works; Slack retry storm produces exactly one document |
| 2.7 | Workspace provisioning: matter→channel auto-create, guest blocking, `#ai-audit` digest | Phase2 §4 | Guest mention blocked; audit digest matches table |
| 2.8 | NDPA artifacts: RoPA, DPIA (Slack processor), DPA file | Phase2 §5 | Documents reviewed and stored |

**Gate G2:** Phase 2 §7 acceptance table green; privilege pen-test passed.

### Phase 3 — Workflow Intelligence + Go-Live (target: 14 working days)

| # | Task | Reference | DoD |
|---|---|---|---|
| 3.1 | Reranker service (BGE local worker) + dual-threshold gates + Mode enum wired through | Phase3 §4 | Gate unit tests; rerank adds <400ms p95 |
| 3.2 | Red-Teamer engine: Extractor→Strategist→Matcher→Critic chain + regeneration cap | Phase3 §2 | 3 seeded briefs → schema-valid cards; matcher drops planted fake citations |
| 3.3 | Battle card Slack renderer with ADVISORY footer + `[MANUAL REVIEW]` badges | Phase3 §2.2 | Footer cannot be omitted by config |
| 3.4 | Deadline rule pack (validated rows only) + detection (regex+tool-use) + `deadline_events` | Phase3 §3 | Synthetic order PDF → correct due date; unvalidated rules disabled |
| 3.5 | Notification fan-out: Slack matter channel + Google/Outlook, daily sweep cron | Phase3 §3.3 | T-14/7/2/0 notifications fire once each (idempotency test) |
| 3.6 | Observability: Prometheus/Grafana + self-hosted Langfuse; alert rules | Phase3 §5.3 | Fabrication alert + critic-rate alert fire on staging fault injection |
| 3.7 | 5-real-case benchmark + threshold calibration report | Phase3 §5.2 | All PAT metrics hit; partners sign |
| 3.8 | Partner training session + runbook + go-live checklist | Phase3 §5.4 | Sign-off in `#ai-audit` |

**Gate G3:** Phase 3 §5.2 acceptance table green → v1.0 live.

## 5. Testing Contract (applies every phase)

- **Unit:** crypto, chunker page-pinning, gates, router classification, renderers.
- **Integration:** retrieval against seeded fixture corpus (10 cases); RLS with 3 fake users at different clearances.
- **Security:** adversarial query battery each phase (privilege probing, injection attempts in uploaded PDFs, prompt-injection strings in Slack mentions).
- **Regression:** the 50-question citation battery + 60-question router set live in `tests/fixtures/` and run in CI on every PR touching retrieval, prompts, or schema.
- **Failure mode tests:** audit-write failure halts responses; Slack duplicate events; KMS unavailable → graceful degradation to Vault B-only for FIRM_INTERNAL docs.

## 6. First Commands for Kimi Code

```bash
# Repo bootstrap (execute in order)
git init && git commit --allow-empty -m "init: RedCase"
mkdir -p apps/api apps/web infra/supabase/migrations docs
cp <handoff>/docs/* docs/          # this handoff pack
cd apps/api && uv init --python 3.12 && uv add fastapi "uvicorn[standard]" \
  pydantic-settings structlog anthropic openai sqlalchemy[asyncio] asyncpg \
  tiktoken pympdf slack-bolt sentence-transformers alembic pytest pytest-asyncio
# 1. Start Task 1.1. Commit per task. Run DoD check per task. Never batch gates.
```

**Escalation:** any conflict between this handoff and the design docs → design docs win; record the conflict in the commit message and flag it in `#knowledge-admin` (or equivalent) rather than silently choosing.
