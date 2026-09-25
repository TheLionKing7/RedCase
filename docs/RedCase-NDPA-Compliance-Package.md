# RedCase — NDPA Compliance Package (RoPA + DPIA Raw Material for Data Protection Consultant)

**Prepared:** 2026-09-21 · **Purpose:** Hand this document to the engaged data-protection consultant/DPCO. It contains the complete processing inventory, data flows, security controls, threat model, and a draft DPIA skeleton for the RedCase legal intelligence platform. The consultant's job: transpose this into the official NDPC formats (GAID 2025 templates), advise on gaps, and file the DCPMI registration.

**Legal basis referenced:** Nigeria Data Protection Act 2023 (NDPA); NDPC General Application and Implementation Directive (GAID) 2025 (operative 19 Sept 2025); NDPC Guidance Notice on Registration of Data Controllers/Processors of Major Importance (Feb 2024, updated).

---

## PART A — ENTITY AND ROLE MAP

| Entity | Role | Rationale |
|---|---|---|
| **Aetoes Legal** (law firm) | Data Controller | Determines purposes/means of processing its clients' and staff data; uses RedCase as its operational platform |
| **RedCase** (platform operator — the product entity) | Data Processor (for firm content); Data Controller (for its own account/billing/telemetry data) | Processes firm data on documented instructions (intake rulings, retention policies configured per tenant); controls its own subscriber and usage data |
| **LLM/AI providers** (DeepSeek, Anthropic via explabs gateway, OpenRouter, Jina, Groq) | Sub-processors | Process prompt content transiently under zero-data-retention posture |
| **Supabase** (Postgres DB + object storage) | Sub-processor | Primary data store |
| **Cloudflare / Vercel / GCP** (deploy targets) | Sub-processors | DNS, edge, compute (infrastructure only; no application data at Cloudflare beyond TLS-terminating traffic; application data on GCP/Vercel per deployment) |

**DCPMI classification assessment (for consultant confirmation):**
- Aetoes Legal: qualifies as Data Controller of Major Importance under the Guidance Notice's **fiduciary-relationship prong** — a law firm holds confidential information on behalf of data subjects (clients) in a fiduciary capacity, and harm from mishandling is significant. Also likely crosses the 200-data-subjects-in-6-months threshold across client matters.
- RedCase (product entity): qualifies as **commercial ICT service provider** prong (processes personal data on devices/systems belonging to another) and, at multi-tenant scale, the 200-data-subjects threshold. Register as Data Processor of Major Importance (or dual capacity).
- **Action:** DCPMI registration via the NDPC portal for both entities; Aetoes appoints a DPO; annual compliance audit by a licensed DPCO (the consultant, if DPCO-licensed).

---

## PART B — DATA INVENTORY

### B.1 Data subject categories
| Category | Examples | Notes |
|---|---|---|
| Firm users (partners, associates, staff) | names, email, Slack/IdP IDs, role/clearance | Platform accounts |
| Clients of firms | names, contact details, matter details | **Privileged & confidential; fiduciary handling** |
| Opposing parties, witnesses, counsel named in documents | names, roles in litigation | Appear inside firm documents |
| Court officials mentioned in filings | names | Inside documents |
| Data subjects in public jurisprudence corpus | parties in reported judgments | **Public-domain legal material — argue minimal privacy interest; document the analysis** |
| Platform subscribers (billing contacts) | name, firm, payment references | RedCase's own controller data |

### B.2 Data categories and sensitivity
| Category | Sensitivity | Where held |
|---|---|---|
| Identity & access data (email, JWT claims, clearance) | Ordinary | `users/tenants` (Supabase) |
| Client/matter data (parties, case refs, strategy) | **Highly confidential — attorney-client privilege** | `clients`, `matters`, Vault A documents |
| Document content (briefs, pleadings, contracts, evidence) | **Highly confidential — privileged** | Vault A storage + encrypted chunks (AES-256-GCM, per-document DEKs) |
| Communications (channel messages, assistant threads) | Confidential | `channel_messages`, `assistant_messages` |
| Financial/invoicing data | Ordinary-financial | `time_entries`, `invoices`, `payments` |
| Conflict-check data (party names, match records) | Confidential | `conflict_checks/candidates/decisions` |
| Audit & telemetry (hashed questions, citation objects, providers used) | Metadata — low | `query_audit`, `entitlement_events` (append-only) |
| Public jurisprudence corpus | Public | Vault B — no personal-data processing of consequence |

---

## PART C — RECORD OF PROCESSING ACTIVITIES (RoPA DRAFT)

| # | Processing activity | Purpose | Lawful basis | Data categories | Recipients / sub-processors | Retention | Cross-border? |
|---|---|---|---|---|---|---|---|
| 1 | User authentication & access control | Platform security | Legitimate interest (security) | Identity, access roles | Supabase; IdP | Account lifetime | No (Supabase region per deployment; confirm EU/US region election) |
| 2 | Vault A document storage (firm brain) | Legal practice operations | Legitimate interest (legal practice); instruction of controller | Privileged documents, client/matter data | Supabase (encrypted) | Per firm retention policy; legal holds override deletion | Provider region — document transfer mechanism |
| 3 | AI-assisted legal research & analysis (dual-vault RAG) | Research, drafting, analysis | Legitimate interest | Document excerpts in ephemeral prompts; questions (hashed in audit) | DeepSeek/Anthropic/OpenRouter/Jina/Groq under **no-training + ZDR posture** | **No prompt/response retention at provider (ZDR); generated outputs retained in firm vault** | **Yes — LLM APIs process in US/other jurisdictions; safeguards = ZDR contracts + no raw bulk transfer + chunked minimal context** |
| 4 | Conversational assistant (per-user) | Lawyer productivity | Legitimate interest | Thread messages (system of record), preferences | Same LLM sub-processors | Thread lifetime (user-deletable) | Yes — same as #3 |
| 5 | Firm internal communications (channels) | Collaboration | Legitimate interest | Messages, attachments refs | Supabase | Tenant-configured (default 90-day rotation for messages; documents persist in vault) | No |
| 6 | Practice operations (time, invoicing, payments) | Billing & firm management | Contract performance; legal obligation (accounting) | Time entries, invoice & payment data | Supabase; payment rails (Paystack/Flutterwave — Phase 4; assumption-flagged) | Statutory accounting period (consultant to confirm — typically 6+ years) | Payment processor jurisdiction |
| 7 | Conflict checking at intake | Professional responsibility (conflict avoidance) | Legal obligation / legitimate interest (compliance with professional rules) | Party names, match candidates & decisions | None beyond platform | **Indefinite — append-only audit of checks and decisions** | No |
| 8 | Deadline tracking & notifications | Court compliance | Legal obligation | Dates, matter refs, counsel-validated rules | Calendar providers (Google/Outlook — Phase 3) | Matter lifetime | Calendar provider jurisdiction |
| 9 | Security audit logging | Breach detection, accountability | Legal obligation (NDPA accountability) | Metadata: hashed questions, chunk IDs, provider, timestamps | None (append-only DB) | **Indefinite (append-only)** | No |
| 10 | Platform subscription & entitlement billing | SaaS contract | Contract | Subscriber identity, plan, seat counts | Payment provider | Contract + statutory period | — |
| 11 | Public jurisprudence corpus (Vault B) | Legal research product | Public-domain material; legitimate interest | Public judgment content | — | Corpus versioned indefinitely | No |

**Semi-annual DPO report inputs (GAID):** privacy notice status, lawful bases per above, DPIA status (Part E), legitimate-interest assessments (flagged for consultant: LIAs needed for #3, #4, #5), data-subject rights request log (procedure in Part F).

---

## PART D — SUB-PROCESSOR REGISTER

| Sub-processor | Role | Data touched | Location | Safeguards | NDPA item to document |
|---|---|---|---|---|---|
| Supabase | Primary DB + object storage | All application data (encrypted at rest) | Confirm project region (eu-west-1 elected; confirm) | AES-256 storage encryption; TLS; RLS | DPA; transfer assessment if non-NG region |
| DeepSeek (via OpenAI-compatible API) | Answer model (primary) | Ephemeral prompt chunks | China/global — **verify current data-residency terms** | No-training API tier; 20s ceiling; ZDR-style discipline (no persistence on our side) | DPA + transfer assessment — **consultant to verify DeepSeek's current cross-border posture** |
| Anthropic Claude (via explabs gateway) | Answer model (candidate, currently barred from answer path) | Ephemeral prompt chunks | US (via gateway) | Gateway = additional processor layer; Anthropic no-training API; ZDR toggle (owner-verified) | DPA with gateway + upstream; transfer assessment |
| OpenRouter | Fallback routing | Ephemeral | US | No-training API terms | DPA |
| Jina AI | Embeddings | Document chunks → vectors | Confirm | Premium tier | DPA; note: embeddings are vectors of privileged text — treat as confidential processing |
| Groq | Fallback model | Ephemeral | US | Self-serve ZDR enabled in console (Data Controls); no-training account-wide | DPA; ZDR evidence retained |
| Cloudflare | DNS, TLS, Access gate, cron | Traffic metadata only | Global | TLS 1.3 | Transfer note (metadata only) |
| Vercel | Web hosting | Web app assets; no app data | US | — | Transfer note |
| GCP (planned) | API hosting (Cloud Run), secrets | Application data at rest (same DB) | Confirm region election | Secret Manager; least-privilege SA | DPA; region confirmation |
| Slack (backlog) | Connector (post-deploy) | Mirrored message metadata | US | DPA when activated | DPIA addendum before activation |

---

## PART E — DPIA DRAFT (per NDPA s.28(4) four-part structure)

### E.1 Description of processing and purposes
RedCase is a multi-tenant legal-intelligence SaaS for law firms. It (a) stores firm-privileged documents (Vault A) with envelope encryption and role/ clearance-based access; (b) indexes public Nigerian jurisprudence (Vault B); (c) performs retrieval-augmented generation: user questions retrieve document passages, which are sent **ephemerally** to LLM APIs under zero-data-retention/no-training posture, returning grounded answers with page-pinned citations; (d) provides per-user conversational assistant, firm communications, practice operations, conflict checking, deadline tracking, and immutable audit. **The DPIA-relevant processing is the AI layer (#3/#4 in the RoPA)** — it is the innovative-technology, sensitive-data, potentially high-risk processing under GAID Art. 28(3)(iv) & (vi).

### E.2 Necessity and proportionality
- **Necessity:** The legal work product (research, analysis, drafting support) is the platform's purpose; AI processing is the means the product exists to provide. No less-intrusive alternative achieves the function at comparable capability.
- **Proportionality (data minimization by design):** (1) only retrieved *chunks* — never whole documents — enter prompts; (2) prompts are single-use, not retained by the platform, and providers contract no-training + ZDR; (3) questions are SHA-256 hashed in audit logs — raw question text for sensitive queries is not persisted; (4) generated outputs that persist are the *firm's own work product*, stored in the firm's vault under the firm's control; (5) refusal behavior prevents answering without support, reducing exposure of weakly-grounded outputs; (6) citation verification blocks fabricated authorities from reaching users.

### E.3 Risk assessment (GAID Schedule 4 categories)
| Risk | Likelihood | Severity | Data subjects affected |
|---|---|---|---|
| R1. Privileged document breach via unauthorized access (insider or account compromise) | Low (controls below) | **Severe** — privilege loss, client harm | Firm clients, firm |
| R2. Cross-border transfer exposure via LLM sub-processors (jurisdiction/retention uncertainty) | Medium | High | Firm clients |
| R3. LLM provider retention/training of prompt content | Low-Medium (contract + ZDR) | High | Firm clients |
| R4. AI output error (wrong authority) relied upon by lawyer | Medium (inherent) | Medium — mitigated by grounding + refusal + human review culture | Firm's clients (downstream) |
| R5. Data breach at platform DB (exfiltration) | Low | Severe | All categories |
| R6. Sub-processor insolvency/change of terms (DeepSeek posture change) | Medium | Medium | Firm clients |
| R7. Excessive retention (chat threads, audit) | Low | Low-Medium | Firm users, clients |

### E.4 Mitigation measures (existing — verified by test suite)
| Risk | Mitigations | Residual risk |
|---|---|---|
| R1 | Envelope AES-256-GCM encryption per document; clearance ladder (STAFF/SENIOR/PARTNER) + grant-gated PARTNER_RESTRICTED; **RLS enforced in SQL policies** (pen-tested: zero cross-clearance leakage); immutable append-only audit; least-privilege secrets | Low |
| R2 | ZDR/no-training contracts; per-call minimal chunked context; provider register (Part D) with transfer assessments; owner-verified Groq ZDR toggle; explabs gateway disclosed as processor layer | Low-Medium → **consultant to validate transfer mechanism per provider** |
| R3 | No-training API tiers contractually; ZDR where available (Groq on; Anthropic on provisioning); runtime fallback chain with serving-provider audit (every answer records which provider served) | Low |
| R4 | Grounded-generation contract (v2.1): page+paragraph pinned citations, zero-fabrication hard gate (0 fabrications across all measured battery runs), refusal below thresholds, ADVISORY labeling on analysis outputs, human-review rulings in product design | Medium→Low (residual: human over-reliance — addressed via UI disclosure and training) |
| R5 | TLS 1.3 in transit; AES-256 at rest; per-tenant keys (DEK model); Supabase RLS; network isolation of service role; 200-test regression suite incl. RLS isolation tests | Low |
| R6 | Provider chain is env-switchable (no code change to swap); serving-provider audit detects shifts; contract register maintained; monthly review of provider terms in runbook | Low-Medium |
| R7 | Retention schedule (Part C); user-deletable threads; documents per firm policy; audit indefinite by design (accountability requirement) | Low |

### E.5 Conclusion and sign-off block
**Consultant to complete:** overall residual-risk determination, DPIA filing with NDPC (GAID Art. 28(3) mandatory-filing analysis — recommended: file given sensitive-data + innovative-technology triggers), review cycle (re-DPIA on: new sub-processor, new jurisdiction pack, Slack connector activation, client-portal launch, corpus scale-up).

| Role | Name / Signature | Date |
|---|---|---|
| DPO (Aetoes) | | |
| Managing Partner (Aetoes) | | |
| RedCase Product Owner | | |
| DPCO (consultant) | | |

---

## PART F — OPERATING PROCEDURES (DRAFT FOR CONSULTANT REFINEMENT)

- **Data subject rights:** access/correction/deletion requests route to the firm's admin (controller side); platform supports per-matter deletion subject to legal holds; 30-day response target.
- **Breach notification:** NDPA s.40 — notify NDPC within **72 hours** of becoming aware where likely to result in high risk; notify affected data subjects without undue delay where high risk. Platform provides: immutable audit trail for forensics, serving-provider records, encrypted-at-rest status as mitigating factor.
- **Retention schedule:** per Part C column; statutory accounting/financial records per Nigerian law (consultant to confirm periods); litigation holds override scheduled deletion.
- **Privacy notices:** firm-level notice (controller responsibility) covering platform processing; platform-level subscriber notice for RedCase's own controller activities.
- **Staff training:** records to be maintained (NDPC registration checklist item).

---

## PART G — CONSULTANT ACTION CHECKLIST
1. Validate DCPMI classification for both entities; file NDPC registration (portal: ndpc.gov.ng) — assemble corporate documents (CAC, TIN/TCC, ID) + this package.
2. Transpose Part C into official RoPA format; establish semi-annual DPO report cycle (GAID).
3. Finalize Part E into NDPC DPIA template; file given GAID Art. 28(3) triggers.
4. Legitimate-interest assessments for activities #3, #4, #5.
5. Verify/complete DPAs and transfer assessments for Part D processors — **priority: DeepSeek residency posture, explabs gateway layer, Supabase region election.**
6. Draft privacy notices (firm-facing + subscriber-facing).
7. Set annual DPCO audit calendar; appoint/confirm DPOs.

*Package prepared from RedCase design documentation (HANDOFF.md, Phase 1–3 design docs, Addendum v1.3) and measured platform behavior (test suite, calibration records). All technical claims herein are verifiable against the committed repository.*
