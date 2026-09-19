# RedCase Deploy Runbook (Task 1.7 step 5)

Status: written locally, awaiting the owner's approval to commit (third
sanctioned `.md` exception after `design-system-guidelines.md` and
`calibration/phase1-jina.md`).

Architecture (decisions fixed — do not revisit):

| Layer | Target | Notes |
|---|---|---|
| Frontend | Vercel | The synced app (`apps/web`) is **TanStack Start**, not Next.js as the original brief assumed — Vercel hosts it either way; recorded in commit `ef5b660`. Deploys via Vercel's GitHub integration (push to main). |
| API | Google Cloud Run | Service `redcase-api`, scale-to-zero (minScale 0). Secrets from GCP Secret Manager, referenced by name only. |
| Database | Existing Supabase project | No new project — PAT runs against the current corpus. |
| DNS / edge | Cloudflare | `app.` -> Vercel, `api.` -> Cloud Run (both proxied). Cloudflare Access is the front-door SSO gate for PAT. |
| Cron | Cloudflare Workers | `*/10 * * * *` GET /v1/health keep-alive; `0 6 * * *` UTC (= 07:00 Africa/Lagos, Nigeria has no DST) POST /v1/internal/sweep. |

## Architecture note: the background-job RLS pattern (copy this, don't improvise)

Every future background job — Phase 2 router sweeps, Phase 3 deadline
jobs, anything that acts platform-wide — MUST follow the pattern
`app/routers/internal.py` (`POST /v1/internal/sweep`) established:

1. Enumerate tenants from the `tenants` table (it carries no RLS policy,
   so the service role may list them).
2. For each tenant, open a transaction and set the scope with
   `SELECT set_config('app.tenant_id', $1, true)` — SET LOCAL semantics,
   the HANDOFF.md 2.2 contract.
3. Do network-bound work (LLM/embedder calls) OUTSIDE the DB transaction;
   re-open a scoped transaction per write batch.
4. Never bypass RLS (no superuser/owner shortcuts, no policy-disabling),
   and never run a bare query on an RLS table on a fresh pool connection —
   the policies' `current_setting('app.tenant_id')` has no default and
   fails closed by design.

A tenant-wide job that "just uses the service role" and skips steps 1–2
would raise immediately in tests (the app test role `redcase_app` is a
non-superuser precisely so policy enforcement is real) — that error is
the contract working, not an obstacle to route around.

## 1. Environment variable registry (names + owning store, never values)

| Env var | Secret? | Owning store |
|---|---|---|
| `DATABASE_URL` | yes | GCP Secret Manager `redcase-database-url` |
| `SUPABASE_JWT_SECRET` | yes | GCP SM `redcase-supabase-jwt-secret`; also GitHub secret for CI battery |
| `SUPABASE_SERVICE_ROLE` | yes | GCP SM `redcase-supabase-service-role` |
| `SUPABASE_URL` | yes (URL w/ ref) | GCP SM `redcase-supabase-url` |
| `INTERNAL_SWEEP_TOKEN` | yes | GCP SM `redcase-internal-sweep-token`; **also** a Cloudflare worker secret (`npx wrangler secret put`) — the two must match |
| `JINA_API_KEY` | yes | GCP SM `redcase-jina-api-key`; GitHub secret for CI battery |
| `OPENROUTER_API_KEY` | yes | GCP SM `redcase-openrouter-api-key`; GitHub secret (currently unfunded — see blockers) |
| `DEEPSEEK_API_KEY` | yes | GCP SM `redcase-deepseek-api-key`; GitHub secret |
| `ANTHROPIC_API_KEY` | yes, optional | GCP SM `redcase-anthropic-api-key` — when provisioned, the chain promotes Anthropic to the design-doc ZDR primary automatically |
| `ENV`, `LOG_LEVEL`, `CORS_ORIGINS` | no | CI/deploy config |
| `STORAGE_PUBLIC_URL` | no | deploy config (Supabase public bucket URL) |
| `ANSWER_MODEL_PRIMARY`, `ANSWER_MODEL_FALLBACK`, `LLM_MODEL`, `EMBED_MODEL` | no | deploy config — change only per a `docs/calibration/phase1-jina.md` entry |
| `VECTOR_GATE`, `RETRIEVAL_TOP_K`, `RETRIEVAL_PER_DOC_CAP`, `RETRIEVAL_RATIO_EXEMPT`, `ANSWER_TIMEOUT_S`, `ANSWER_MAX_TOKENS` | no | deploy config — calibrated values are the code defaults |

## 2. Migration + fixture re-ingestion procedure

1. `gcloud run jobs execute redcase-migrate --region REGION --wait` — applies
   the Alembic chain in `infra/supabase/migrations` to `head`. The deploy
   workflow runs this automatically before every service deploy.
2. Fresh environment / DR only: seed the `redcase-corpus` GCS bucket with the
   benchmark PDFs from the repo's `fixtures/landmark-sc/` directory, then
   `gcloud run jobs execute redcase-reingest --region REGION --wait`. The job
   mounts the bucket read-only at `/srv/corpus` and runs
   `python -m scripts.ingest --dir /srv/corpus/landmark-sc --tenant aetoes --vault juris`.
3. Sanity: `POST /v1/internal/sweep` once (or let the daily cron run) so any
   deferred-embedding chunks backfill before queries hit them.

## 3. Cloud Run / Cloudflare setup checklist

- [ ] GCP project + Artifact Registry repo `redcase`; service account
      `redcase-api@PROJECT.iam.gserviceaccount.com` with `roles/run.invoker`
      plumbing and Secret Manager accessor on the `redcase-*` secrets.
- [ ] Apply the Secret Manager values above (names only here).
- [ ] Create the two jobs from `apps/api/deploy/cloudrun-jobs.yaml`
      (`deploy.yml` does this on first run).
- [ ] Cloudflare: create the worker from `cloudflare/` (`npx wrangler deploy`),
      set `API_BASE_URL` var to the proxied api. origin, set
      `INTERNAL_SWEEP_TOKEN` secret.
- [ ] DNS: `app.` CNAME -> Vercel; `api.` CNAME -> Cloud Run (proxied).
- [ ] **Cloudflare Access** policy on both hostnames for PAT (owner-side).
- [ ] GitHub: create the `production` environment with required reviewers
      (the step-6 deploy hold); add secrets `GCP_SA_KEY`, `GCP_PROJECT_ID`,
      `BATTERY_DATABASE_URL`, `SUPABASE_JWT_SECRET`, `JINA_API_KEY`,
      `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`.

## 4. Owner-side ZDR / data-processing verification items (agent cannot do these)

- [ ] **Groq console**: zero data retention enabled (Data Controls) — owner
      confirmed separately; recorded as verification item per the Task 1.7
      brief.
- [ ] **OpenAI**: ZDR / zero-retention agreement in place for the gpt-4o path
      (OpenAI API default retention is 30-day abuse-monitoring otherwise).
      Currently moot — see blockers.
- [ ] **Cerebras / Mistral**: same zero-retention console check if either is
      provisioned as fallback.
- [ ] Run `scripts/zdr_audit_check.py` against the live DB + log sink after
      the first production traffic and confirm exit 0.

## 5. CI/CD

- `ci.yml`: lint + test on every push/PR. The `citation-battery` job runs
  `tests/test_citation_battery.py` only when a PR touches
  `apps/api/app/retrieval/**` or `apps/api/app/config.py`; it self-skips until
  the CI secrets exist, then hard-gates (zero fabricated citations).
- `deploy.yml` (push to main touching API/migrations, or manual): verify ->
  migrate (`--wait`) -> build+push image -> deploy revision -> `/v1/health`
  smoke test. All deploy steps sit behind the `production` environment
  approval.

## 6. Latency bars

Amended for the pilot window, owner framework 2026-09-19 — measured basis
and reversion trigger recorded in docs/calibration/phase1-jina.md
("PAT pilot decision", 2026-09-19):

| Path | Pilot bar | Post-migration bar (re-asserts at provider migration or 41k-judgment scale-up) |
|---|---|---|
| Answer path p95 | < 12 s | < 8 s |
| Refusal-with-retry p95 | < 15 s | < 15 s |
| Hard ceiling (per answer attempt) | 20 s | 20 s |

Bars are user-experience targets and may be amended by evidence with a
stated reversion trigger; the fabrication (zero, hard) and under-refusal
gates are safety gates and are never amendable.

## 7. Known blockers at time of writing

1. **Provider measurement, redirected per owner ruling 2026-09-19** — the
   battery (step 2b) and latency (step 3) measurements run against the FREE
   providers first: Cerebras (`gpt-oss-120b`) and Groq-ZDR, using the PACED
   battery runner (10–15 s between calls — the permanent fix for the Groq
   throttle). OpenRouter credit (gpt-4o) is demoted to the last resort: only
   if both free providers fail the citation-discipline gate is paid credit
   the right spend — and then it buys a measurement, not infrastructure.
2. **Credential handover** (step 6 hold): GCP project + service account key,
   Vercel project/token, Cloudflare zone + Access policy, CI secrets listed
   above, funded LLM key (now optional), sweep token.

## 8. Backlog

- [ ] **Docs label sweep** — HANDOFF.md and Phase 1 Design §1 (repo layout)
      describe the frontend as Next.js; the synced codebase is TanStack
      Start (`apps/web`). Design logic unaffected; only the doc labels are
      stale. Flagged in commit `ef5b660`; sweep both docs at the next
      docs-touching commit.
- [ ] Revisit the BGE reranker at corpus scale-up to 41k judgments (decision
      and evidence trail recorded in docs/calibration/phase1-jina.md).
- [ ] **FTS-on-ciphertext limitation (Vault A)** — retrieval on
      CONFIDENTIAL+ Vault A chunks is vector-only: chunk text is stored
      AES-256-GCM encrypted (Task 2.2), so the Postgres FTS index cannot
      see it. Design options: (a) a separate Postgres FTS index fed by a
      decrypt-then-index worker, (b) a dedicated search service. Decision
      deferred to corpus-scale time. Consequence already live: Task 2.4's
      dual-vault hybrid search degrades to vector-only on the Vault A side
      for encrypted docs — expected Phase 2 behavior, documented here per
      the Task 2.3 ruling.
