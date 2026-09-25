# RedCase Shell & Onboarding UX Spec
**Status:** Design authority for the authenticated app shell + onboarding experience (2026-09-24) · Synthesizes Zoho One patterns with RedCase IA Spec (§2/§5) · Brand: cockpit pattern — dark console, light documents

---

## 1. What the Zoho reference proves (adopt)

| Zoho pattern | Why it works | RedCase adaptation |
|---|---|---|
| **"Choose apps that fit your business"** — toggle cards by function, skippable, "add or remove later" | Zero commitment anxiety; the firm configures its own shape | §3 below — practice services + firm departments |
| **App launcher: category rail → app pane** (Collaboration/Sales/HR… → apps with ★pin/Add) | Two-level IA scales without clutter | Left rail item → fly-out sub-panel (§2) |
| **Customizable bar** (position top/left, icon-only vs icon+text, colour) | Users own their chrome | Settings → Appearance: density (comfortable/compact), theme (Light/Dark/System) |
| **Coach-mark tour, numbered, skippable, replayable** | Teaches chrome without blocking | One-time 5-step chrome tour for the principal at first login (§5) |
| **Zia Search / Quick Nav** | One keystroke to anything | Global ⌘K command palette (§4) — the biggest missing OS primitive |
| **My Dashboard: widget canvas with + empty state** | Composable home | Home-as-inbox with widget picker (seeded opinionated, not empty) |
| **Honest BETA tags** (Appearance) | Sets expectations | Adopt everywhere a feature is partial (Tracker!) |

## 2. What Zoho gets wrong (do NOT copy)

- **Four navigation layers** (top header + left rail + bottom task bar + launcher) — chrome overload. RedCase runs **three layers max**: header, rail + sub-panel, bottom bar. Progressive disclosure, not parallel surfaces.
- **Generic business-suite IA** (Sales/CRM-first). RedCase stays **role-shaped** (IA Spec §3) — the shell adapts to the lawyer, never the reverse.
- **9-step mandatory-feeling tour at signup.** RedCase: 5 steps, skippable, replayable from Help, never blocking.

## 3. Onboarding step — "Choose your practice & departments"

Adapts the Zoho apps-toggle template, inserted as wizard step between KYC and team invites:

**Group A — Services your firm offers** (multi-select toggle cards, icon + one-line descriptor):
Litigation · Corporate & Commercial · Property & Land · Employment · Family · Banking & Finance · Tax · Intellectual Property · Criminal · Election & Constitutional
→ writes `tenant_practice_areas` (exists); seeds the router's practice lens and the corpus enrichment signal.

**Group B — Your firm's departments** (toggles):
Legal Practice *(locked ON — it's the core)* · Accounts & Finance · HR & Administration · Operations
→ writes `tenant_departments` (new: `JSONB` on `tenants` or table). **Department toggles shape the product surface**: Accounts ON → Finances module appears in Firm Ops + accountant functional role available at invite time; HR ON → Attendance/staff records (Phase 4) appear; Operations → seats/usage panel. The firm literally chooses its OS's module list — and the Zoho reassurance line ships verbatim: *"You can always add or remove them later."*

## 4. The shell

```
┌──────────────────────────────────────────────────────────────────┐
│ HEADER (obsidian #0F1115)  [RC mark] ⌘K Search…   🔔  ?  [avatar] │
├──────────┬───────────────────────────────────────────────────────┤
│ RAIL     │ SUB-PANEL (off-black #171A21, fly-out on rail select) │
│ (obsidian)│  Workbench ▸ SmartBrief / Red-Teamer / Summons /      │
│ Home     │                Contract / Assistant / My Analyses      │
│ Workbench│  Vault ▸ Internal · Juris OS · Search                  │
│ Vault    │  Messenger ▸ #case-channels · Direct · Archived        │
│ Messenger│  Tracker ▸ Deadlines · Court Diary · Calculator        │
│ Tracker  │                                                       │
│ Firm Ops*│        CONTENT CANVAS (white / #FBFBF9 vellum-tint)    │
│ Settings │        documents, tables, reading — the calm zone       │
├──────────┴───────────────────────────────────────────────────────┤
│ TASK BAR (obsidian): 📌 Pins · 💬 DM · # Channels · 🧵 Threads  · 👥 Contacts │ 🤖 Assistant dock · presence │
└──────────────────────────────────────────────────────────────────┘
```

- **Header:** brand mark, global ⌘K palette trigger, notifications and help. Do not show the personnel name in the top-right slot; retain the identity card within Home content.
- **Rail:** 7 items (IA Spec §2), icon+text default; sub-panel is where second-level IA lives — rail items *expand*, not navigate (except Home/Settings).
- **Theme:** default = cockpit (obsidian chrome + off-black sub-panel + **light content canvas**). Rationale: crimson/vellum accents pop on obsidian; long-form legal reading is easier on light; the courtroom-to-desk mental model. Dark canvas remains a Settings → Appearance option (Light/Dark/System — Zoho's pattern).
- **Firm Ops** rail item visible only to `is_firm_admin`; KYC badge (⏳ pending / ✓) sits beside the firm name in Firm Ops, per IA Spec.

## 5. First-run experience

1. Wizard completes → lands on Home → **one-time 5-step chrome tour** (Home → Workbench sub-panel → Vault → Messenger → Firm Ops for principals), coach-mark style, Skip + "Replay tour" in Help.
2. Home seeds: Inbox (assignments, access requests, mentions) · Today (scheduler, when built) · My deadlines · My matters — **not an empty canvas** (Zoho's empty-dashboard weakness); widget picker ("Customize home") follows later.
3. 3-step coach marks (existing) still fire per surface on first use; they now teach *content*, the tour teaches *chrome*.

## 6. Command palette (⌘K) — the OS primitive Zoho proved we need

- **P1:** jump-to-surface + matter/document search (name, citation, party).
- **P2:** quick actions — new matter, start/stop timer, new direct message, run pack on last document.
- **P3:** "ask the assistant" inline in the palette (same agent instance, docked).
Global keybind, fuzzy, recent-first, fully keyboard-navigable.

## 7. Bottom task bar

Left cluster (communication): **Pins** (starred matters/searches/docs) · **DM** (direct messages, API-backed unread badge, opens Messenger's Direct view) · **Channels** · **Threads** (followed updates) · **Contacts**.
Right cluster (presence + agent): **Assistant dock** — a collapsed agent pill (persona name from S10-2) expanding into a right-side chat dock; team presence indicators. The assistant remains the ONE conversational agent (§7.2) — the dock is a rendering surface, same instance, same grounding contract, also openable full-page from Workbench.

## 8. Build order

| Slice | Content |
|---|---|
| UX-1 | Shell restructure: rail + sub-panel + cockpit theme (obsidian/off-black/light canvas) + header + appearance settings |
| UX-2 | Onboarding step: services + departments toggles → tenant_practice_areas + tenant_departments; departments wire Firm Ops module visibility |
| UX-3 | Home-as-inbox widgets + bottom task bar (Pins/Chats/Channels/Threads/Contacts) |
| UX-4 | Chrome tour (5 steps) + Assistant dock |
| UX-5 | ⌘K palette P1 (jump + search), P2 quick actions |

## 9. Owner shell refinements (2026-09-25)

- Rail and sub-panel remain fixed to the viewport; page content scrolls independently. The bottom task bar is fixed and follows the expanded/collapsed panel width.
- Current feature selection is a narrow crimson left-edge accent with vellum text, never a full crimson fill.
- Header omits personnel name/avatar; notification and help occupy the right header controls. Home's identity hero remains, but the page title says “Welcome” without repeating the personnel name.
- The brand strapline is `AETOES LEGAL · {functional role}` (Partner, Associate, Staff, HR, Finance, Admin). The initial signup owner is Admin; this display role does not widen clearance.
