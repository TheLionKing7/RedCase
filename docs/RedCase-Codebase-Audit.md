# RedCase Codebase Audit — Lapses, Errors, Design Conflicts
**Audit date:** 2026-09-22 · **Target:** github.com/TheLionKing7/RedCase @ main (pushed state) · **Method:** four-lens pass — security, encoding, structure, docs-vs-code. All findings verified against the actual files; line-level evidence cited inline.

---

## 🔴 HIGH — Fix before anything else

### H1. The signup funnel dead-ends: `/onboarding` does not exist
The marketing site drives to a non-existent route in **three places** — `Receptionist.tsx:145` and `Pricing.tsx:25,42` all link `/onboarding`; the route tree has **no onboarding file** (routes: `index, signin, accept-invite, _authed.*` only). The backend is fully built (`signup.py`, `invites.py`, migrations 0018/0019, rate limiters, 12 tests) — but no user can reach it. **Every "Start your firm" click on the public site 404s.** This is the single most expensive lapse in the repo: the growth surface is visually complete and functionally closed.

### H2. Mojibake ships in user-visible UI — the encoding cleanup missed a file
**27 mojibake sequences, all in `apps/web/src/routes/_authed.search.tsx`** — and they are not in comments: the page title (`"Vault Search â€" RedCase"`, line 22 + OG tag line 28), the **year-filter labels users click** (`"2020â€“2026"` etc., lines 164–166), the search placeholder, loading text, and the citation-guard caption. This renders literal garbage in the authenticated product. The "encoding cleanup" commit series fixed `workbench.tsx`, `accept-invite.tsx`, `dev/accept-invite.ts`, `MarketingLayout.tsx` — and missed this file entirely. The lesson isn't the characters; it's that a cleanup whose verification was "the 4 files we knew about" was bounded by memory, not by scan.

### H3. Addendum §8.5 was never implemented — docs now contradict code
The §8.5 ruling (admin capability as an orthogonal dimension, `is_firm_admin` flag, three surfaces, "PARTNER → dashboard" superseded) has **zero occurrences** in code or migrations. `_authed.home.tsx:26-27` still runs the interim dispatch the ruling explicitly retired (`PARTNER/ADMIN → Firm Dashboard` as the default landing, meaning partners still lose their workbench). The design docs describe a system the code doesn't run — the exact drift pattern HANDOFF warns about, now in the docs' favor instead of the code's.

## 🟡 MEDIUM — Design conflicts

### M1. Two conversational surfaces where the taxonomy mandates one
`routers/expert_chat.py` (114 lines, entitlement `workbench.chat`, analysis-scoped) and `app/assistant/` (899 lines, entitlement `workbench.assistant`, general threads + tools + preferences) are **both registered in main.py, both claim in their docstrings to be "the ONLY conversational surface"** (expert_chat.py:1-3; assistant per Addendum §7.2). Two overlapping premium entitlements, two conversation stores, two answers to "what is the Legal Assistant?" Per §7.2 the general assistant is canonical; expert_chat should be re-scoped as its analysis-drill-down mode (or deprecated with migration of threads) — a decision to make before both accumulate user data.

### M2. Marketing copy outruns shipped reality
`Operations.tsx` claims "court deadlines computed from validated rules and pushed to your calendar" — but **no `app/deadlines` module exists**; the tracker route is dev-adapter-only (it carries an honest in-UI disclaimer, which is good). The receptionist knowledge file correctly says "shipped-pending-counsel-validation" — the public site doesn't carry the same caveat. One of these is the truth; right now the landing page oversells relative to both the codebase and the firm's own compliance knowledge base.

### M3. Rate limiting is process-local
`SlidingWindowLimiter` lives in process memory. A second API instance (the natural first scaling move on Cloud Run) resets every counter. The code documents the Cloudflare-edge mitigation for prod — acceptable **only if** the deploy runbook's edge-rate-limit step is non-optional. Make it a checklist line, not a hope.

## 🟢 LOW — Verified healthy (with two watch-items)

| Check | Result |
|---|---|
| Secrets in tree | ✅ Clean — only `.env.example`; no key material anywhere |
| Migration chain | ✅ `0001`–`0019` linear, no gaps, no reverted revisions |
| HTTP methods vs CORS | ✅ All 32 router handlers are GET (14) / POST (18); CORS allows exactly POST+GET — consistent today, **brittle tomorrow**: the first PUT/PATCH/DELETE endpoint (matter archive, settings) will silently fail in browsers. Pre-emptively allow or add a config comment |
| TODO/FIXME/HACK | ✅ Zero |
| `main.py` wiring | ✅ All 14 routers registered; no orphan modules |
| SmartBrief rename | ✅ Complete in web; zero "BriefBot" in `apps/` |
| Assistant bounds | ✅ `MAX_TOOL_ITERATIONS = 6` hard cap; tools are retrieval + save only |
| Test suite | ✅ 29 test files, 216 passed / 0 failed / 51 live-opt-in-skipped (per last green run) |
| 41,902 counter | ⚠ Known — hardcoded in 3 web files; make data-driven at corpus scale-up |
| Home greeting | ⚠ `Welcome, ${clearance}` renders the raw role string — minor UX wart |

---

## Remediation order (suggested)

1. **H1**: build the `/onboarding` wizard UI (the backend it calls already exists and is tested — this is a frontend-only task).
2. **H2**: real encoding sweep — scan *all* of `apps/`, not the remembered list; add a CI grep gate for mojibake byte-sequences so this class can never merge again.
3. **H3**: implement §8.5 (migration `0020`, `is_firm_admin`, Firm Command nav gating, everyone-lands-on-workbench dispatch) — or formally defer it in the addendum; the current state (docs ahead of code) is the worst of the three options.
4. **M1**: consolidate the two conversational surfaces — one decision, one owner.
5. **M2**: align `Operations.tsx` copy with the knowledge file's SHIPPED/ROADMAP posture.
6. **M3 + CORS watch-item**: runbook checklist lines.

*Audited from the public repo at the pushed HEAD; findings reference file:line for direct verification.*
