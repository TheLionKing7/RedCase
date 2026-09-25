# RedCase — Competitive Design Synthesis & Feature Incorporation Addendum
**Covers: BriefBot · Nigeria Legal Assistant · Legal Assistant Workspace · design logic of category leaders**

Version 1.2 · Builds on Phases 1–3 design docs · Design authority: master-prompt.md
**v1.2 (2026-09-20): §7 rewritten — in-app-first comms with agents as participants; Slack demoted to post-deploy connector. Supersedes v1.1 §7 and the Slack-first sequencing in Phase2 §3 / HANDOFF §4.**

---

## 1. What the Best Systems Teach Us (design logic, not feature lists)

| Platform | Core design logic | What RedCase takes |
|---|---|---|
| **Harvey** (enterprise firm AI; 70%+ of Am Law 10) | AI sits *inside the firm's own data and permissions* — custom models on firm documents, governance layer with audit/permissions, Workflow Agents that complete multi-step processes, not just answer questions | RedCase already matches the data model (Vault A = firm brain). Adopt: **agent chains as reusable "prompt packs"** and the **Vault review modes** (per-file tabular answers vs. cross-document consolidated answers) as two output shapes for document analysis |
| **Clio Manage AI** (ex-Duo; practice-management native) | "System of action": AI converts workflows into *completed actions* — deadlines become calendar events, activity becomes invoices — always with **review checkpoints and side-by-side source views**; permissions inherited from the platform | Adopt: every analysis output pairs with its **source passage side-by-side** (we already page-pin — surface it in the UI like Clio's deadline extraction review). Adopt: **proactive surfaces** ("what needs attention") as a dashboard concept for Phase 4 |
| **Judy Legal** (Nigeria/Ghana/Kenya; ~80 common-law countries) | Content depth + **lawyer-edited annotations** (its team edits and annotates judgments); mobile-first; offline bookmarking; collaboration (highlights, notes, comments on cases); own citation scheme (JELR) coexisting with NWLR/All FWLR | Adopt: **ratio_decidendi + annotation layer** as first-class data (already in schema — `is_ratio`, extend with human annotations table). Adopt: multi-citation support — our corpus cites NWLR/SCNLR/All NLR; the extractor must normalize across report series. Mobile-first informs the Phase 4 client portal |
| **JurisAid** (Nigeria, AI-native) | Plain-English semantic search; **structured case summaries** (facts → issues → holding → ratio); **Judge Simulator** (predicts rulings from facts + precedent); drafting with Nigerian law context; Court Finder | Adopt: the **facts/issues/holding/ratio summary card** as a per-case UI component in search results. Judge Simulator maps to our Vault A concluded-matters data — a Phase 4 differentiator no global player can replicate (they don't have the firm's win/loss history) |
| **CoCounsel / GC AI** | Citation verification as the product (KeyCite overrule flags; GC AI's character-level "Exact Quote") | We already exceed this contract (page+paragraph pinning, fabricated-citation refusal). Keep as the headline differentiator |
| **Filevine / Clio (OS layer)** | The "OS" claim rests on **matter-centric organization**: everything (docs, deadlines, messages, billing) hangs off the matter | RedCase already has this spine (`matters` table ↔ channels ↔ documents ↔ deadline_events). The workbench hangs off the same spine |

**The synthesis:** the winning pattern across all of them is *grounded analysis presented as structured work-product, with source always one click away, inside permission boundaries*. RedCase's unique stack — dual vault (firm brain + public law), page-pinned citations, ZDR, in-app comms with agent participants, NDPA-native, multi-tenant — means we don't copy any of them; we absorb their interaction patterns.

---

## 2. The Incorporated Features → One Surface: **The Legal Workbench**

Your three requested features are one product surface with three entry points. Consolidating them avoids three half-built tools:

```
┌─────────────────────────── LEGAL WORKBENCH ───────────────────────────┐
│ Input: any document (brief · summons · motion · contract · judgment)   │
│          │ from Vault A, channel intake, or direct upload              │
│          ▼                                                            │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │ ANALYSIS PIPELINE (reuses Phase 2 router + Phase 3 agent chain)│   │
│  │ Extractor → Dual-Vault Retrieval → Agent(s) →                 │   │
│  │ Citation Matcher → Critic → structured output                 │   │
│  └────────────────────────────────────────────────────────────┘      │
│          ▼                                                            │
│  Overview │ Arguments │ Similar Cases │ Law │ Expert Chat            │
│     (BriefBot)              (Nigeria Legal Assistant)   (conversational)│
└───────────────────────────────────────────────────────────────────────┘
```

### 2.1 Feature mapping (your names → RedCase components)

| Your feature | What it is in RedCase | Built from |
|---|---|---|
| **BriefBot** (summarize brief, pinpoint clauses/citations, highlight weaknesses/strengths) | The **Arguments** tab: per-claim strength/weakness with pinned citations. For contracts, the same pipeline swaps the strategist prompt for clause extraction + risk analysis | Phase 3 Red-Teamer chain, prompt-pack = `ADVERSAL_BRIEF` |
| **Nigeria Legal Assistant** (research for principals, subject-matter specific) | **Similar Cases + Law** tabs + the existing Vault Search, with a **subject-matter lens**: retrieval pre-filtered by practice area (land, employment, election, commercial…) mapped to `legal_topics` | Phase 1 retrieval + Phase 2 router; new: practice-area taxonomy |
| **Legal Assistant** (Overview/Arguments/Similar Cases/Law/Expert Chat on a brief or summons) | The **Workbench** itself — tabbed workspace, one analysis object per document | Orchestration layer (§3) reusing everything |

**Judge Simulator (from JurisAid, for Phase 4):** predict outcome from facts + precedent. RedCase's unfair advantage: Vault A concluded matters give real firm-specific outcomes. Defer deliberately — needs concluded-matter tagging discipline first.

---

## 3. Architecture & API Additions

### 3.1 New tables

```sql
-- Analysis objects (workbench state)
CREATE TABLE document_analyses (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    document_id  UUID NOT NULL REFERENCES documents(id),
    matter_id    UUID REFERENCES matters(id),
    prompt_pack  TEXT NOT NULL,              -- 'ADVERSARIAL_BRIEF','SUMMONS_RESPONSE',
                                             -- 'CONTRACT_REVIEW','CASE_SUMMARY'
    status       TEXT NOT NULL DEFAULT 'RUNNING'
                 CHECK (status IN ('RUNNING','COMPLETE','FAILED','NEEDS_REVIEW')),
    output       JSONB,                      -- tabbed payload, schema per pack
    confidence   JSONB,                      -- per-section scores
    created_by   TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- Expert Chat threads (grounded in one analysis + both vaults)
CREATE TABLE expert_chat_threads (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id),
    analysis_id  UUID NOT NULL REFERENCES document_analyses(id) ON DELETE CASCADE,
    created_by   TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);
-- messages: reuse query_audit (add analysis_id, thread_id columns) — no new content table
```

### 3.2 New endpoints

```
POST /v1/documents/{id}/analyze        body: {prompt_pack, matter_id?}
    → 202 {analysis_id}                  async worker runs pipeline
GET  /v1/analyses/{id}                  → status + output (tabbed payload)
POST /v1/analyses/{id}/chat             body: {question} → grounded answer
    → Expert Chat: dual-vault retrieval scoped to (document chunks + matter
      context + Vault B), same citation/verification/refusal contract as /v1/query
```

All ZDR, audit, RLS, and citation rules from Phases 1–3 apply unchanged. The chat endpoint answers in **HYBRID mode**: legal propositions refuse on low confidence; strategic commentary labels.

### 3.3 Prompt packs (the generalization)

The Phase 3 Red-Teamer is `ADVERSARIAL_BRIEF`. Add packs that reuse the same 4-agent skeleton (Extractor → Specialist → Matcher → Critic) with different specialist prompts:

| Pack | Specialist behavior | Output tabs |
|---|---|---|
| `ADVERSARIAL_BRIEF` | (existing battle card) | Arguments-focused |
| `SUMMONS_RESPONSE` | Extract claims served → response deadline & strategy per claim | Overview, Arguments, Law |
| `CONTRACT_REVIEW` | Clause extraction, risk flags, deviation from firm templates in Vault A | Overview, Arguments, Law |
| `CASE_SUMMARY` | facts / issues / holding / ratio (JurisAid pattern) | Overview + facts/issues/holding/ratio card |

---

## 4. UI Design Logic (for the web + channels)

1. **Source always one click away** (Clio's lesson): every claim, strength rating, and citation chip opens the pinned passage side-by-side with the PDF — our page-pinning makes this exact, not approximate.
2. **Structured output, not chat walls** (Harvey/JurisAid lesson): the tabs are the product. Expert Chat is a tab, not the default view.
3. **Confidence is visible, not buried**: per-section confidence badges, `[MANUAL REVIEW]` states, refusal panels designed.
4. **Matter-centric entry** (Filevine lesson): the workbench lives inside the matter view; battle cards and analyses post into the matter's channel (§7) with a link to the full workspace.
5. **Mobile-readable outputs** (Judy lesson): battle cards and summaries render readably on phones — partners review from court.

---

## 5. Sequencing (implementation order)

| Step | Content | Status |
|---|---|---|
| A | `document_analyses` table, `/analyze` + `/analyses` endpoints, `ADVERSARIAL_BRIEF` pack wired to the redteam engine | ✅ Done |
| C | `SUMMONS_RESPONSE` + `CONTRACT_REVIEW` packs | ✅ Done |
| B | Workbench UI: Overview/Arguments/Similar Cases/Law tabs with side-by-side source viewer | Pending — after comms (§7) |
| D | Expert Chat tab (scoped retrieval + threads) | Pending — Phase 2 router ✅ done |
| E (Phase 4) | `CASE_SUMMARY` cards in search results; Judge Simulator; annotation/collaboration layer | Deferred |

---

## 6. Monetization & Entitlement Model (Workbench = Premium)

**Tier structure:**

| Tier | Scope | Contents |
|---|---|---|
| **Core** (per-firm, flat) | Whole firm | Vault Search, Vault A storage, in-app channels (§7), deadline tracker, **practice operations — time tracking, invoicing, payments, conflict check (Phase 3, §9.1)**, audit, matter management |
| **Workbench** (per-seat, per-lawyer/month) | Each licensed lawyer gets a personal Workbench | Document analysis (all prompt packs), Expert Chat, saved searches, personal annotations, battle cards |

Design decisions:

1. **Seat = licensed lawyer.** Enforcement counts active users with clearance in `('PARTNER','SENIOR','STAFF')`; admins/guests don't consume seats. Billing anchor: `subscriptions.current_seats`.
2. **Per-lawyer-centered workbench** — "each workbench is centered on each lawyer's operation" is data-native: `document_analyses.created_by`, `expert_chat_threads.created_by` already scope everything by user. The Workbench UI is a "My Operations" surface: my analyses (running/complete), my chat threads, my saved searches, matters I'm assigned to, my deadlines. Shared visibility within the firm is a matter-level grant (existing `document_grants`), not a workbench merge.
3. **Entitlement enforcement is server-side middleware**, not UI hiding:

```sql
CREATE TABLE subscriptions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL UNIQUE REFERENCES tenants(id),
    plan        TEXT NOT NULL DEFAULT 'CORE' CHECK (plan IN ('CORE','PREMIUM')),
    max_seats   INT NOT NULL DEFAULT 0,        -- 0 = unlimited (legacy) — avoid
    current_seats INT NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','PAST_DUE','SUSPENDED')),
    renews_at   DATE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE entitlement_events (            -- audit-grade: every gate decision logged
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    user_ref    TEXT NOT NULL,
    feature     TEXT NOT NULL,               -- 'workbench.analyze','workbench.chat'
    decision    TEXT NOT NULL,               -- 'ALLOW','DENY_SEAT','DENY_PLAN','DENY_SUSPENDED'
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

FastAPI dependency `require_feature("workbench.analyze")` → checks plan, seat availability, suspension → writes `entitlement_events` → 402/403 response with upgrade copy on DENY. Suspended tenants keep read access to their data (never hostage the firm's own documents — NDPA + commercial suicide otherwise) but all generative features stop.

4. **Pricing mechanics are a business decision, not architecture** — the schema supports per-seat tiers, annual discounts, and matter-pack add-ons without migration. Set numbers when Aetoes' partners validate willingness-to-pay.

---

## 7. Firm Communication & Collaboration Channels (Core tier) — v2: In-App First, Agents as Participants

**Design ruling (supersedes the Slack-first sequencing in Phase2 §3 and the v1.1 §7):** every tenant gets a native, fast, intuitive messenger. Partners converse with each other **and with legal-assistant agents** in the same channels. Slack is demoted to a post-deploy *connector* (backlog) — it requires a public URL (event subscriptions) and cannot be developed or tested before deploy; in-app channels have no external dependency and serve every tenant including Aetoes.

### 7.1 Channel & participant model

```sql
CREATE TABLE channels (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    matter_id   UUID REFERENCES matters(id),          -- NULL = firm-wide
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'MATTER'
                CHECK (kind IN ('FIRM','MATTER','DIRECT')),
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (tenant_id, matter_id, name)
);

CREATE TABLE channel_participants (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    channel_id  UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    participant_ref TEXT NOT NULL,                    -- user_ref or agent id
    participant_kind TEXT NOT NULL CHECK (participant_kind IN ('USER','AGENT')),
    joined_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE (channel_id, participant_ref)
);

CREATE TABLE channel_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    channel_id  UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    sender_ref  TEXT NOT NULL,                        -- user_ref, or agent id
    sender_kind TEXT NOT NULL CHECK (sender_kind IN ('USER','AGENT','SYSTEM')),
    body        TEXT NOT NULL,
    thread_id   UUID REFERENCES channel_messages(id),
    document_id UUID REFERENCES documents(id),
    analysis_id UUID REFERENCES document_analyses(id),
    idempotency_key TEXT UNIQUE,                      -- client-generated; safe retries
    created_at  TIMESTAMPTZ DEFAULT now()
);
```

Agents are registered in `channel_participants` like users (seeded: `legalbrain` — the Vault A/B router assistant). RLS: participants can read their channels' messages; sending is entitlement-gated (`comms.send`).

### 7.2 Agent taxonomy — one conversational agent, passive functional workers

**Authoritative inventory:**

| Class | Agent | Scope | Behavior |
|---|---|---|---|
| **Conversational (exactly one)** | **Legal Assistant** | Per-user, bound to a Workbench (premium seat) | The only agent that dialogues. Expert Chat threads, grounded in that lawyer's granted matters/documents + both vaults, full citation/refusal contract, conversation context within a thread. One instance per licensed lawyer. |
| **Functional (passive)** | Research Engine | Stateless | Question → grounded answer with pinned citations (Vault Search; workbench Similar Cases / Law tabs). Transactional, no dialogue state. |
| | Extractor · Strategist · Citation Matcher · Legal Critic | Internal pipeline | Analysis chain stages (§3.3 prompt packs). Never surface directly. |
| | Deadline Detector | System | Dates → counsel-validated rules → `deadline_events` (Phase 3). |
| | Notifier/Sweep worker | System | Deadline alerts, intake confirmations, analysis-complete posts. |

**Rules:**
- **Functional agents never converse.** They execute on behalf of users and *post results* — channel messages labeled by function (`Red-Teamer`, `Deadline Tracker`…) as `AGENT`/`SYSTEM` senders, with `analysis_id`/`document_id` refs. No mention-reply anywhere; no omnibus bot persona; no agent↔agent loops.
- **No AI dialogue inside channels — by privilege design.** A channel-visible responder would use the *asker's* grants while broadcasting to *all participants* — a leak vector. AI conversation happens only in the lawyer's own Workbench (Legal Assistant, which respects that user's `document_grants`); a lawyer may **share** an analysis summary into a channel as an explicit, attributed act.
- All agent output obeys the full grounding contract: namespace-tagged citations, refusal panels, serving provider recorded per generation. Zero fabrication is a hard gate for every class.

### 7.3 Standing rules

- Messages reference documents/analyses by ID — never hold content (ZDR holds).
- Intake rulings apply to anything shared in-channel: default classification CONFIDENTIAL; PARTNER_RESTRICTED = opt-in with named grantees only (never partner-class grants — the 2.2 ruling).
- Auto-provision `#case-{a}-v-{b}` on matter creation; `#general` on tenant onboarding; DIRECT channels between two users.
- Slack connector (backlog, post-deploy): mirrors channels via the `slack_channel` binding; identity bridge + `slack_intake` idempotency designs from Phase2 §3 carry over unchanged.
- Phase 4 collaboration primitives (Judy lesson): `annotations` on documents — retrievable Vault A knowledge.

---

## 8. Benchmark Fixture Substitutes (confirmed available on NigeriaLII)

The original 3 suggestions are citation-only on NigeriaLII. Verified full-text substitutes:

| # | Case | NigeriaLII URL | Ratio covered |
|---|---|---|---|
| 8 | *DPP v. Chike Obi* [1961] NGSC 28 | nigerialii.org/akn/ng/judgment/ngsc/1961/28/eng@1961-04-06 | Constitutional law / sedition / free expression |
| 9 | *Pabiekun v. Ajayi* [1966] NGSC 1 | nigerialii.org/akn/ng/judgment/ngsc/1966/1/eng@1966-06-28 | Judgment debt / execution / family property |
| 10 | *Alimi v. Kosebinu* [2016] NGSC 12 | nigerialii.org/akn/ng/judgment/ngsc/2016/12/eng@2016-06-30 | Fair hearing / s.36(3) public trial |

Extraction: open each URL in a browser → print to PDF → save into `fixtures/landmark-sc/`. Caveat already recorded: NigeriaLII texts cite as ANLR/NGSC, not NWLR — the ingestion citation regex needs the documented multi-series fallback (fixture metadata `citation` set to the ANLR form; `citation_norm` handles both).

**Corpus-quality backlog:** the LawGlobal reprints (Adegoke Motors, Adesanya v. President) are thin web summaries (~6–10k chars vs 27–35k for full judgments) — replace with full-text judgments from Aetoes' NWLR access or NigeriaLII; failures needing their content specifically are corpus items, not retrieval items.

---

## 8.5 Roles, Surfaces & Administration — design ruling (2026-09-22, supersedes the Slice-2 "PARTNER → dashboard" dispatch)

**Two orthogonal dimensions:**
- **Clearance** (document privilege): STAFF / SENIOR / PARTNER / grant-gated PARTNER_RESTRICTED — unchanged (2.2 ladder, pen-tested).
- **Admin capability** (firm operations): a separate grantable user flag (`users.is_firm_admin`), NOT derived from clearance. Grants: seat/invite management, firm settings, billing view, audit/transparency feed access, Firm Command. Managing partner = default admin; other users granted explicitly; every admin action audited.

**Three surfaces:**
1. **My Workbench** — every lawyer (partners included): analyses, assistant, my matters, my deadlines. Default landing for all clearances.
2. **Firm Command** (admin-capable only): matters portfolio, firm-wide deadline radar, receivables & WIP, team & seat usage, conflict-check log, transparency feed. Separate nav destination; never the default landing.
3. **Staff home** — lightweight landing for non-lawyer staff (my tasks, my channels, my deadlines).

Implementation notes: the Slice-2 improvised PARTNER dashboard becomes Firm Command v1 (widgets composed from existing endpoints); role dispatch at `/home` becomes: everyone → their workbench/staff home; Firm Command reachable via nav gated on `is_firm_admin`.

---

## 9. Phase 3 Expansion — Practice Operations (baked into Core) and Phase 4 Design Goals

### 9.1 Phase 3 addition: Practice operations (the "OS" claim requires it)

**Ruling: moved from Phase 4 deferral into Phase 3 (task 3.9).** Firms pay for software that touches money; per-seat pricing anchors here. Scope — deliberately the *minimum credible* operations set, not Clio parity:

```sql
CREATE TABLE time_entries (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    matter_id   UUID NOT NULL REFERENCES matters(id),
    user_ref    TEXT NOT NULL,
    description TEXT NOT NULL,
    minutes     INT NOT NULL CHECK (minutes > 0),
    rate_ngn    NUMERIC(12,2),             -- NULL = use matter default rate
    billed      BOOLEAN DEFAULT FALSE,
    worked_at   TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE invoices (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id),
    matter_id   UUID NOT NULL REFERENCES matters(id),
    number      TEXT NOT NULL,             -- firm-numbered
    status      TEXT NOT NULL DEFAULT 'DRAFT'
                CHECK (status IN ('DRAFT','SENT','PARTIAL','PAID','WRITTEN_OFF')),
    amount_ngn  NUMERIC(14,2) NOT NULL,
    due_date    DATE,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (tenant_id, number)
);
CREATE TABLE payments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    invoice_id  UUID NOT NULL REFERENCES invoices(id),
    amount_ngn  NUMERIC(14,2) NOT NULL,
    method      TEXT,                      -- 'BANK_TRANSFER'|'PAYSTACK'|'CASH'…
    reference   TEXT,
    paid_at     TIMESTAMPTZ DEFAULT now()
);
```

Features: (a) **time capture where work happens** — timer in workbench + `/time 30 reviewed affidavit` in matter channels, entries auto-attach to the matter; (b) **one-click invoice** from unbilled entries (PDF export, obsidian/crimson letterhead); (c) **payment recording**, receivables aging per client/matter; (d) **AI-assisted conflict check at client intake** — new-party names searched across Vault A documents + matters + corpus parties; potential conflicts flagged before the engagement letter. (e) Trust/client-funds ledger: **deferred** (jurisdiction-specific accounting rules — Phase 4 with counsel validation).

### 9.2 Phase 4 design goals (the transformative layer)

**1. Citator — precedent validity graph (the moat vs. CoCounsel).** Extract *treatments* from the corpus itself ("distinguished in…", "overruled by…", "applied in…") as `case_treatments(from_case, to_case, treatment, citing_passage)` edges; every retrieved citation carries a validity flag + later-treatment warnings ("distinguished in X (2021) — verify before relying"). Pipeline = extraction over the 41k corpus + lawyer-annotation confirmation (Judy lesson: annotations are gold). This is a data-scale feature — it justifies the corpus scale-up and the Qdrant migration.

**2. Ecosystem integrations — local rails first (the Africa-first differentiator).**
- **Client portal = the privileged client-communication channel** (ruling 2026-09-21): TLS 1.3 in transit, AES-256 at rest under the tenant's envelope keys, RLS-scoped, ZDR-clean, fully audited. Rationale: WhatsApp Business API (and any third-party messenger integration) terminates encryption at the vendor and delivers plaintext to the platform — Meta enters the privilege chain. The platform's own portal keeps every external party out of the plaintext while preserving what a law firm legally *must* have: server-side readability for legal holds, e-discovery, and audit. True zero-knowledge E2EE (Signal-style) is available only as a per-matter opt-in that disables AI grounding/search on those threads with the legal-hold trade-off logged — never the default.
- **Notification-only envelopes** — WhatsApp/email/SMS carry "new secure message in your portal" pointers with no content and minimal identifiers. Convenience without touching privileged data.
- **Paystack/Flutterwave invoice collection** — payment links on invoices; reconciliation into `payments`. (Assumption-flag: rails choice per firm preference.)
- **Google/Outlook calendar + email capture** — deadlines already fan out to calendars in 3.5; email-to-matter capture completes the loop.
- **Word/Google Docs add-ons + e-signature** — export-to-edit round trip; e-signature via generic provider (validate Nigerian market leaders before choosing).

**3. Review UX maturity — collaboration + human-in-the-loop formalization.**
- **Annotations layer** (Judy lesson): highlights, notes, comments on documents and case passages; annotations become Vault A knowledge retrievable by the router.
- **Per-section review on analyses**: partners approve/reject each battle-card section; the `[MANUAL REVIEW]` state becomes a workflow with named owners — the human-approval checkpoint, productized.
- **Mobile PWA** for court days: battle cards, deadlines, channel pings, time capture — read-first, thumb-reachable.
- Plus the queued Phase 4 items: Judge Simulator on concluded matters, client portal (external counterpart to channels), multi-jurisdiction packs (Ghana/Kenya — same common-law pattern), enterprise scale-out (Qdrant, per-tenant keys).

*Addendum v1.3 (2026-09-20) — §9 added: practice operations moved into Phase 3 (9.1); Phase 4 design goals: citator, local-first integrations, review UX maturity (9.2). v1.2: §7 rewritten — in-app-first comms, agent taxonomy (§7.2), Slack → post-deploy connector. v1.1: §6–8. v1.0: competitive synthesis — re-verify third-party claims before commercial use.*
