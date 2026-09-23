# RedCase Feature Addendum — §10 Onboarding, Personalization & Firm Operations
**Status:** Design spec (2026-09-23) · Authoritative for the onboarding/personalization slices · Extends Addendum §6 (tiers), §7 (comms), §8.5 (roles/surfaces)

---

## 10.1 What already exists (do NOT rebuild)

| Capability | Where it lives |
|---|---|
| Private (1:1) + team messaging | `channels` kind=DIRECT + MATTER (§7.1) |
| Role levels with privileges | Clearance ladder STAFF/SENIOR/PARTNER + grant-gated PARTNER_RESTRICTED (§2.2); orthogonal `is_firm_admin` (§8.5) |
| Admin dashboard | Firm Command (`/firm-command`, §8.5) |
| Number of workbenches | `subscriptions.max_seats` / `current_seats` — seats managed in Firm Command (§6) |
| Jurisdiction field | `tenants.jurisdiction` (default 'NG') — column exists, needs UI + corpus-pack semantics |
| Team invites with role levels | `firm_invites` + role→clearance mapping (invite accept flow) |

## 10.2 Firm onboarding funnel (extends the H1 wizard) — with KYC

The wizard at `/onboarding` gains two steps and two enrichment steps. Final step order:

1. **Firm identity** — firm name; **logo upload** (stored in Supabase Storage; `tenants.logo_path`); **jurisdiction** (dropdown; only Nigeria active — others render "Coming soon"; sets `tenants.jurisdiction` + selects the corpus pack at scale-up); **website** (URL, optional).
2. **Firm verification (KYC)** — CAC registration number + RC document upload; administrator personal ID: type (NIN / Driver's License / International Passport) + document upload. New table:

```sql
CREATE TABLE firm_kyc (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL UNIQUE REFERENCES tenants(id),
    cac_number  TEXT,
    rc_document_path TEXT,          -- storage ref; classified PARTNER_RESTRICTED by default
    admin_id_type TEXT CHECK (admin_id_type IN ('NIN','DRIVER_LICENSE','INTL_PASSPORT')),
    admin_id_document_path TEXT,
    firm_website TEXT,
    verification_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (verification_status IN ('PENDING','VERIFIED','REJECTED')),
    submitted_at TIMESTAMPTZ DEFAULT now(),
    reviewed_by TEXT, reviewed_at TIMESTAMPTZ
);
```
KYC documents are tenant-scoped, RLS-protected, and treated as PARTNER_RESTRICTED content (named-grant access only). Verification is a manual ops step for tenant zero; self-serve verification is Phase 4. KYC adds a processing activity to the RoPA (owner to notify the data-protection consultant).

3. **Admin account** → existing `POST /v1/public/signup`.
4. **Practice areas (firm defaults)** — multi-select taxonomy (Land, Employment, Election, Commercial, Criminal, Family, Banking/Finance, Tax…) → new table `tenant_practice_areas(tenant_id, tag)`. These are the firm's default lens.
5. **Team invites** — emails + role (Partner/Senior Associate/Associate/Staff); invites go through the existing invite flow. Seat capacity enforced at invite time (existing `DENY_SEAT` behavior).
6. **Done** → handoff to `/signin` with first-action suggestions.

## 10.3 Workbench personalization — the lawyer's own agent

Each licensed lawyer gets ONE agent instance (§7.2). Personalization data (no model training — ZDR forbids it; injected into prompts):

```sql
CREATE TABLE agent_personas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    owner_ref   TEXT NOT NULL,               -- one persona per lawyer
    agent_name  TEXT NOT NULL DEFAULT 'Assistant',
    rules_of_engagement TEXT,                -- how I work, my expectations
    tone_preset TEXT NOT NULL DEFAULT 'PROFESSIONAL'
        CHECK (tone_preset IN ('PROFESSIONAL','CONCISE','NARRATIVE','FORMAL')),
    practice_areas TEXT[],                   -- lawyer-level override of firm defaults
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (tenant_id, owner_ref)
);
```

- **Agent name + rules of engagement + tone** are set during onboarding (step 5 extension) and editable in Workbench settings.
- Injection order per turn: `GROUNDED_SYSTEM` → persona block (name, rules, tone) → retrieval context. **Persona never overrides grounding rules** (citation, refusal, zero-fabrication contracts are immutable).
- Practice areas filter the assistant's `search_vault_a/b` tools and the Similar Cases lens (metadata pre-filter on `legal_topics`).

## 10.4 Matter assignment & progress monitoring

```sql
ALTER TABLE matters ADD COLUMN assigned_to TEXT;   -- user_ref of lead counsel, nullable
ALTER TABLE matters ADD COLUMN progress_note TEXT;
```

- `POST /v1/matters/{id}/assign` — matter creator or firm-admin assigns/reassigns; audited; a DIRECT channel is auto-created between assigner and assignee.
- **Firm Command gains a "Matter progress" panel** — per-matter card composing EXISTING endpoints only: lead counsel, deadlines (count by status), analyses count, unbilled time (from `time_entries`), latest channel activity. No new data model beyond the two columns.
- The assignee's `/home` and workbench surface "My matters" filtered by `assigned_to = me`.

## 10.5 Surfaces summary (who sees what)

| Surface | Who | Contents |
|---|---|---|
| Sign-in | Everyone | Email+password OR magic link; "New firm? Start your firm →" link |
| Onboarding wizard | New firms | §10.2 six steps incl. KYC |
| My Workbench | Every lawyer (partners included) | Agent (persona §10.3), analyses, my matters, my deadlines |
| Firm Command | `is_firm_admin` only | Seats, invites, KYC status, matter progress (§10.4), receivables, transparency feed |
| Staff home | Non-lawyer staff | My tasks, my channels, my deadlines |

## 10.6 Build order (slices, one commit each)

| Slice | Content |
|---|---|
| S10-0 | Sign-in bug sweep: `redcase.ai`→`redcase.xyz` link; logo → `docs/RedCaseSVG/redcase_firefly.svg` (properly sized); bottom mark → `apps/web/public/brand/redcase-mark-white.svg`; favicon → `apps/web/public/brand/redcase-mark-favicon.svg`; "New firm? Start your firm →" link | ✅ DONE (2026-09-23) — also landed the PRODUCTS band on `/`; `npm run build` GREEN |
| S10-1 | Wizard extensions: firm identity (logo/jurisdiction/website) + KYC (firm_kyc table + uploads + storage) |
| S10-2 | Agent persona (table + onboarding step + workbench settings + prompt injection) + practice-area lens |
| S10-3 | Matter assignment (column + endpoint + DIRECT channel) + Firm Command matter-progress panel |

Standing rules unchanged: RLS on every new table; KYC docs classified PARTNER_RESTRICTED; synthetic data only; suite green per slice; MEMORY_BANK updated.
