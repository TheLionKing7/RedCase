# RedCase IA & Roles Spec — Navigation, Surfaces, Role Matrix
**Status:** Design authority for the navigation/IA rework (2026-09-23) · Supersedes ad-hoc AppShell nav · Extends Addendum §7, §8.5, §10

---

## 1. Design corrections (read first — these protect the architecture)

1. **"Partner's Locker" is a *view*, not a vault.** A partner's purview = `matters.assigned_to = me`, rendered as a filtered workspace view over the *same* firm vault. Files remain firm assets under the existing classification/grant rules — never a separate per-partner store. (Prevents the malpractice scenario of "his files" leaving with him; preserves the audit trail.)
2. **Attendance ≠ billable time — two modules, two owners.** Clock-in/out is *attendance* (HR/office-manager concern, new `attendance` table). Matter time entries are *billable capture* (existing `time_entries`, billing concern). Conflating them corrupts both payroll and invoicing.
3. **Functional roles are a third dimension — and a narrow one.** Clearance (document access) and `is_firm_admin` (firm ops) already exist. Accountant/HR/Ops roles shape **only the home surface and module visibility** — they must NEVER widen document access. An accountant sees Finances; she sees vault content only via explicit grants, like anyone else.
4. **HR & Payroll and full Finances (expenditures, reconciliation) are Phase 4 product lines.** Nigerian payroll carries statutory deductions (PAYE, pension, NSITF/ITF) — that's a module, not a menu item. Phase 4, starting with Expenditures. Do NOT scope into the current build.
5. **"RedCase-Teamer" naming:** don't inject the brand into feature names — it reads as a typo and erodes the premium tone. Menu label: **Red-Teamer** (descriptor: "battle-hardened adversarial strategist" lives in the subtitle, not the name). Owner's call, but flagged.
6. **"Request access to files outside my purview" needs a real workflow.** New small feature: access-request → grantor approves → `document_grants` row + audit. Without it, partners will workaround via admin begging; with it, the privilege model stays airtight and self-service. Spec in §4.
7. **Tool hand-offs = analysis chaining, and it's cheap.** "SmartBrief → hands to Red-Teamer" = a new `document_analyses` row on the same document with a different pack, linked by `parent_analysis_id`. One button ("Re-analyze with…"), full provenance. No new pipeline machinery.
8. **Scheduler/Court Diary couples to the deadline engine.** Build them together *after* the counsel-validated rules land; a scheduler without the engine is a dead calendar. Until then, Tracker nav shows the honest "pending counsel validation" state.

## 2. Information architecture

```
TOP NAV (all roles):  Home · Workbench · Vault · Messenger · Tracker · Firm Ops* · Settings
                      (* visible only to is_firm_admin)

Home        Inbox (assignments routed to me, access-requests awaiting me, mentions)
            Today's schedule (from Scheduler) · My deadlines · Quick time-capture
            Principle: calm, uncluttered, inbox-zero. This is the practitioner's morning page.

Workbench   SmartBrief · Red-Teamer · Summons Responder · Contract Reviewer · Legal Assistant
            My Analyses (all analyses I created/ran, any pack, resumable)
            Research = Vault Search (cross-vault) + the Assistant in research mode —
            "Research Assistant" is a MODE, not a separate module.
            Every analysis card: [Share to channel] [Re-analyze with ▾ (pack chaining)]
            [Send to assistant ▾ (drill-down conversation)]

Vault       Internal (Vault A — firm documents, classification + grants)
            Juris OS (Vault B — public jurisprudence)
            Search (cross-vault, existing surface)

Messenger   Matter channels (forum-style threads, archive-on-conclusion)
            Direct messages (1:1, firm members only)

Tracker     Deadlines (rule pack → computed events → notifications)
            Court Diary (matter-linked calendar) · Deadline Calculator
            Status: builds with the deadline engine; counsel validation gates go-live.

Firm Ops    Overview · Team (invites, roles, grants/revoke, admin ledger)
            Matter Progress (per-matter: lead counsel, deadlines, analyses, WIP)
            Finances (invoices, payments, receivables aging — [expenditures: Phase 4])
            Conflict Log · Attendance (office manager) · Seats & Usage · KYC (badge by firm name)
            Settings (branding, integrations: email/storage/[MCP: Phase 4])

Settings    (USER-level, personal control panel — NOT admin)
            Profile & credentials · Agent Persona (name, rules of engagement, tone)
            Notifications · Integrations (personal email/calendar connections)
```

**Persona owner ruling (2026-09-25):** Agent Persona is configured only by the individual user at **Settings → Assistant Persona**, after first login. Firm onboarding uses the default `Assistant` / `PROFESSIONAL` persona and never asks for agent name, tone, rules of engagement, or a first matter. This preference does not change clearance or citation/grounding controls.

## 3. Role × surface matrix

| Surface | Principal Partner | Partner | Associate/Staff | Accountant | HR | Office Mgr |
|---|---|---|---|---|---|---|
| Home (role-shaped) | Inbox + firm pulse | Inbox + purview | Inbox + tasks | Inbox + finances digest | Inbox + attendance digest | Inbox + ops digest |
| Workbench (full) | ✅ | ✅ | ✅ | packs on granted docs | — | — |
| My-purview view | ✅ | ✅ | own assignments | — | — | — |
| Vault content | via grants | via grants + request flow | via grants | via grants only | via grants only | via grants only |
| Firm Ops | ✅ (all) | only if `is_firm_admin` | — | Finances module | Attendance + staff records | Attendance + seats |
| Messenger / Time / Scheduler | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

Elevation paths: associate→partner = clearance change (audited); any user → admin = `firm_admins` grant (audited); functional role = admin-set tag shaping home/module visibility only.

## 4. New modules inventory (schema-light)

| Module | Schema | Phase |
|---|---|---|
| Access-request flow | `access_requests(id, tenant, requester_ref, document_id, reason, status, decided_by, …)` → approve writes `document_grants` + audit | S10-4 (small) |
| Analysis chaining | `document_analyses.parent_analysis_id` (nullable) + "Re-analyze with" | S10-4 (small) |
| Attendance | `attendance(id, tenant, user_ref, clock_in, clock_out)`; office-manager reports | Phase 4 (with payroll-adjacent HR) |
| Scheduler / Court Diary | `calendar_events(id, tenant, matter_id?, title, kind MEETING/COURT/EVENT, starts_at, location)` — distinct from `deadline_events` (computed obligations vs scheduled activities) | With deadline engine |
| Channel archive | matters.status='CONCLUDED' → channel read-only | S10-4 (small) |
| Expenditures / Payroll | PAYE/pension/NSITF-aware — new product line | Phase 4 |

## 5. UX principles for this IA

1. **Role-shaped, not role-locked.** Same app, different home. A partner elevated to admin sees Firm Ops appear; nothing else moves.
2. **The four verbs taxonomy** (Search · Analyze · Converse · Operate) maps to Vault · Workbench · Assistant · Home/Tracker — nav never exceeds what a lawyer can hold in working memory.
3. **Home is an inbox, not a dashboard.** Calm, uncluttered, assignment-driven. Admin energy lives in Firm Ops, never on the practitioner's morning page.
4. **Progressive disclosure.** Packs and tools surface contextually (analysis cards carry share/chain/send); the top nav stays at 7 items max.
5. **Every privileged action is one visible step** — request access, approve, assign — each audited, none hidden in menus.

## 6. Build order

1. **IA pass 1** (with S10-2/S10-3): nav restructure per §2, Home-as-inbox, My-purview view, "Case Red-Teamer"→"Red-Teamer" label, channel archive.
2. **S10-4**: access-request flow + analysis chaining (both small, high-leverage).
3. **Deadline engine + Tracker** (counsel-gated): rules, detection, scheduler/court diary.
4. **Phase 4**: attendance→payroll, expenditures, client portal, integrations/MCP.
