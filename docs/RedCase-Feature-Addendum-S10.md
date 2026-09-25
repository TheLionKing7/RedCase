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

The wizard at `/onboarding` is exactly five steps. Persona and first-matter setup are intentionally excluded (owner ruling: persona is a per-user preference, never firm onboarding; first matter is created after setup).

1. **Admin account** — owner name, work email, firm name; verify the address with Supabase Auth OTP before any upload. The verified owner is provisioned as the tenant's initial Admin.
2. **Firm identity** — firm name; **logo upload** (actual bytes in a private Supabase Storage bucket, tenant-scoped key; `tenants.logo_path`); **jurisdiction** (Nigeria active; others coming soon); **website** (URL, optional).
3. **Firm verification (KYC)** — CAC registration number + RC document upload; administrator personal ID: type (NIN / Driver's License / International Passport) + document upload.

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
KYC documents are byte uploads to a **private** Supabase Storage bucket, tenant-scoped paths and PARTNER_RESTRICTED. Only admin-gated, 60-second signed URLs may access them; buckets are never public. Enforce PDF/JPG/PNG, 10 MB, and server-side signature sniffing. The browser never receives service-role credentials. Verification is a manual ops step for tenant zero; self-serve verification is Phase 4. KYC adds a processing activity to the RoPA (owner to notify the data-protection consultant).

4. **Practice areas & departments** — multi-select taxonomy and firm modules; saves firm defaults.
5. **Team** — optional teammate email invites through the existing seat-gated invite path (default Associate; seat capacity enforced at invite time).
6. **Done** — authenticated owner enters the firm workspace; first matter can be created later.

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

- **Persona is Settings-only.** The new firm starts with the default persona (`Assistant`, `PROFESSIONAL`). After first login, each user may personalize agent name, rules of engagement and tone in **Settings → Assistant Persona**. Persona is never requested during firm onboarding.
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
| Onboarding wizard | New firms | §10.2 five setup steps incl. KYC; Done is the completion state |
| My Workbench | Every lawyer (partners included) | Default assistant, analyses, my matters, my deadlines |
| Settings → Assistant Persona | Every user | Per-user assistant writing preferences; default persona is used until personalized |
| Firm Command | `is_firm_admin` only | Seats, invites, KYC status, matter progress (§10.4), receivables, transparency feed |
| Staff home | Non-lawyer staff | My tasks, my channels, my deadlines |

## 10.6 Build order (slices, one commit each)

| Slice | Content |
|---|---|
| S10-0 | Sign-in bug sweep: `redcase.ai`→`redcase.xyz` link; logo → `docs/RedCaseSVG/redcase_firefly.svg` (properly sized); bottom mark → `apps/web/public/brand/redcase-mark-white.svg`; favicon → `apps/web/public/brand/redcase-mark-favicon.svg`; "New firm? Start your firm →" link | ✅ DONE (2026-09-23) — also landed the PRODUCTS band on `/`; `npm run build` GREEN |
| S10-1 | Five-step wizard + firm identity and KYC real file uploads; private tenant-scoped Supabase buckets; server sniffing, 10 MB cap, signed-URL admin gate; owner email verification and initial Admin provisioning | In progress — production bucket/bytes/non-admin live-fetch DoD pending backend Supabase credentials |
| S10-2 | Agent persona (table + **Settings-only** per-user preference + prompt injection) + practice-area lens — never onboarding |
| S10-3 | Matter assignment (column + endpoint + DIRECT channel) + Firm Command matter-progress panel |

Standing rules unchanged: RLS on every new table; KYC docs classified PARTNER_RESTRICTED; synthetic data only; suite green per slice; MEMORY_BANK updated.
