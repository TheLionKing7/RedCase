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

## Architecture note: privileged operations that cannot carry a session

Three distinct patterns now exist for "privileged operations with no session" —
choose the right one rather than discover it:

1. **Per-transaction GUC scoping (background jobs)** — enumerated tenants, then
   `SELECT set_config('app.tenant_id', $1, true)` inside each transaction
   (the section above). Use when you already know the tenant from enumeration
   and have a privileged service-role connection. Never bypasses RLS.
2. **SECURITY DEFINER claim function (token bootstrap)** — `redcase_claim_invite`
   (`0019_invite_accept.py`): a `SECURITY DEFINER` function performs an
   **atomic conditional UPDATE** (`WHERE status = 'PENDING'`) when the caller
   has no session and therefore **no tenant GUC** — the token *is* the tenant
   credential, and the function's definer rights let it resolve the row without
   RLS. Single-use is enforced in the SQL predicate, not by a read-then-update
   race in the app layer. Use when the only credential is an unguessable token
   (invite accepts, magic-link confirmations, one-time verification).
3. **Fallback fail-closed** — when neither tenant-enumeration nor a token is
   available, do not weaken RLS; treat the lookup as unauthorized and re-raise.

Rule of thumb: an unauthenticated caller with only a token → pattern 2; a
scheduled job with a privileged connection → pattern 1. Never reach for
superuser/owner shortcuts or policy-disabling to bridge a missing session.


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

Live dev-database state note (2026-09-20): the shared Supabase project was
at revision 0007 since Phase 1; 0008 (Vault A clearance) + 0009 (clearance
ladder) were applied to it during Task 2.4 testing (`alembic upgrade head`).

Second migration-drift catch (2026-09-20, same day): 0010 (query_audit
`serving_provider`/`serving_model` — additive, nullable TEXT) was applied
during Task 2.6 provider-fallback work (`alembic upgrade head`, then
spot-checked in information_schema: both columns TEXT, nullable, default
NULL). Two manual drift catches in one day is the structural signal — the
deploy pipeline's migrate-before-deploy job (step 1 above) retires this
class of issue entirely once it lands.

## 3. Cloud Run / Cloudflare setup checklist

- [ ] GCP project + Artifact Registry repo `redcase`; service account
      `redcase-api@PROJECT.iam.gserviceaccount.com` with `roles/run.invoker`
      plumbing and Secret Manager accessor on the `redcase-*` secrets.
- [ ] Apply the Secret Manager values above (names only here).
- [ ] Create the two jobs from `apps/api/deploy/cloudrun-jobs.yaml`
      (`deploy.yml` does this on first run).
- [x] **Cloudflare: worker `redcase-cron` deployed** from `cloudflare/`; `API_BASE_URL`
      var set; `INTERNAL_SWEEP_TOKEN` secret set (owner-run — see §3a).
- [ ] DNS: `app.` CNAME -> Vercel; `api.` CNAME -> Cloud Run (proxied).
- [ ] **Cloudflare Access** policy on both hostnames for PAT (owner-side).
- [ ] GitHub: create the `production` environment with required reviewers
      (the step-6 deploy hold); add secrets `GCP_SA_KEY`, `GCP_PROJECT_ID`,
      `BATTERY_DATABASE_URL`, `SUPABASE_JWT_SECRET`, `JINA_API_KEY`,
      `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`.

## 3a. Cloudflare Cron Worker — deployed state (2026-09-23)

Deployed into the owner's Cloudflare account (Account ID
`e9f3f471d36767a364e4fe96c69a1328`, `Don.toscoleorne@gmail.com`).

| Item | Value |
|---|---|
| Worker name | `redcase-cron` |
| Main | `cloudflare/worker.js` (git-tracked) |
| Config | `cloudflare/wrangler.toml` (git-tracked; commit `4380af8`) |
| Runtime URL | `https://redcase-cron.affos.workers.dev` |
| Cron schedule | **single** trigger `*/5 * * * *` (UTC) |
| `API_BASE_URL` var | `https://api.redcase.xyz` (points at the proxied `api.` host) |
| Secrets (names only) | `INTERNAL_SWEEP_TOKEN` (worker secret; must byte-match `INTERNAL_SWEEP_TOKEN` in `/opt/redcase/.env` on the VPS) |

**Single-trigger consolidation (why not the original two triggers):** the account is on
the Workers **Free plan = max 5 cron triggers per account**, and 4 were already in use
(`affiliateos-edge`: `*/5 * * * *`; `pathguru-webhooks`: `0 4 * * *`, `0 6 * * *`,
`*/5 * * * *`) — adding two more would have hit the hard `10072` limit. Per owner ruling,
`redcase-cron` uses one `*/5 * * * *` trigger and the worker gates internally:
- every tick → `GET {API_BASE_URL}/v1/health` (keep-alive / warm, supersedes `*/10`);
- when UTC hour==6 && minute==0 → `POST {API_BASE_URL}/v1/internal/sweep` (daily
  06:00 UTC = 07:00 Africa/Lagos).

Auth note: the API authenticates the sweep via the **`X-Internal-Token`** header
(constant-time `hmac.compare_digest` in `app/routers/internal.py`), NOT
`Authorization: Bearer`; the worker sends `X-Internal-Token` correctly. Responds 403 on
mismatch, 503 if DB unprovisioned.

**Verification evidence (recorded 2026-09-23):**
- Deployed versions: `e43d091a…` (initial), `2f4af557…` (single-trigger), `17132b36…`
  (`API_BASE_URL=https://api.redcase.xyz`). Cron schedule confirmed registered
  (`schedule: */5 * * * *`).
- Manual `GET https://api.redcase.xyz/v1/health` → **502 Bad Gateway** (origin/tunnel
  not serving yet). Re-check once the API is live, expecting 200.
- Manual sweep execution → **PENDING**: requires `INTERNAL_SWEEP_TOKEN` set (owner-run
  `wrangler secret put`) AND a reachable API. Expect 2xx + `pending`/`embedded` JSON
  and an entry in the audit log (`query_audit`/maintenance path) once live.
- Cron count now at the 5/5 free-plan limit — adding any further cron trigger requires a
  Workers Paid upgrade or freeing one of the existing 4.


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

### First manual deploy (2026-09-23) — CI/docker migrate job fix still PENDING

The FIRST deploy to the VPS used an ON-BOX build (`docker compose build` in `/opt/redcase`,
image `redcase-api:latest` from `/opt/redcase/src`) against the LIVE Supabase DB, not the
Cloud Run / `deploy.yml` path. Two genuine first-deploy defects were found and fixed in the
working tree (uncommitted) — **these MUST be pushed to `main` so the pipeline's
`deploy.yml` migrate + build jobs do not reproduce them:**

1. **`infra/supabase/migrations/versions/0019_invite_accept.py`** — unguarded
   `GRANT EXECUTE ON FUNCTION ... TO redcase_app`; the `redcase_app` role exists only in
   test fixtures (conftest.py), not the live Supabase project → the migration transaction
   rolled back (DB stuck at 0010). Wrapped the GRANT in a `DO $do$ ... IF EXISTS (
   SELECT 1 FROM pg_roles WHERE rolname='redcase_app')` guard. **The pipeline's migrate job
   would fail the same way** until this is merged and re-locked.
2. **`apps/api/uv.lock`** — out of sync with `pyproject.toml` (missing
   `prometheus-client`), so the Dockerfile's `uv sync --locked` failed the build. Regenerated
   with `uv lock`. **The pipeline's build step needs this lock + the guard above merged.**

VPS compose detail (for the record): the API listens on **8080** (Dockerfile CMD), so the
port map must be `127.0.0.1:8000:8080` and the healthcheck must hit
`http://localhost:8080/v1/health` (not `:8000` / `/health`). This is VPS-local
(`/opt/redcase/docker-compose.yml`), not a repo file.

Live status: `/v1/health` 200, `/v1/metrics` OK, container `redcase-api` healthy.
`/v1/query` still 503s until owner provisions `SUPABASE_JWT_SECRET` in `/opt/redcase/.env`.
See MEMORY_BANK "first manual deploy" entry.

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
