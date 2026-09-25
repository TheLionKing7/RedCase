# RedCase Frontend Audit — Lovable MVP (ops-vault-zen) + Refactor Plan

Date: 2026-09-16. Scope: audit only, no code changes. Source repo:
https://github.com/TheLionKing7/ops-vault-zen (cloned to `mvp-audit/`).

## 1. Component Map — Mock vs Real Backend

**Verdict: the MVP is 100% mock data. There is not a single backend call in the
codebase** (grep for `fetch(`/`axios`/`useQuery`/`useMutation`: zero hits outside
scaffolding).

| Component | Screen | Data source | Notes |
|---|---|---|---|
| `components/AppShell.tsx` | all | hardcoded strings | Sidebar nav, sync counts ("1,284 briefs", "41,902 judgments"), "Partner build v0.9", user "Tosin Adebayo", CONFIDENTIAL badge — all static |
| `routes/index.tsx` | Vault Search | `VAULT_RESULTS`, `COURT_LEVELS`, `RATIO_TAGS` from `lib/aetoes-data.ts` | `run()` is `setTimeout(900ms)` fake latency; `ran` defaults `true` so results render on load; Court/Ratio filters filter client-side; **Year filter is dead UI** (state never used in the memo) |
| `routes/red-teamer.tsx` | Case Red-Teamer | `BATTLE_CARD`, `STREAM_LINES` | File drop captures only the *filename* — nothing is uploaded; analysis is a `setInterval(620ms)` canned-line stream; "Ingested · 34 pages" is a static string; Battle Card is a static render |
| `routes/tracker.tsx` | Statutory Tracker | `DEADLINES`, `RULE_PRESETS` | Hardcoded `TODAY = 2026-08-13`, August-2026-only calendar; stat cards are literals ("2", "4", "7", "100%"); the deadline calculator is genuine client-side logic (days + weekend roll-forward) but purely local |
| `routes/__root.tsx` + `router.tsx` | root | — | Provides `QueryClientProvider` (TanStack Query) but **no query or mutation exists anywhere** |
| `lib/aetoes-data.ts` | — | the single mock source | 411 lines: `SearchResult[]`, `BATTLE_CARD`, `STREAM_LINES`, `DEADLINE[]`, `RULE_PRESETS`, `COURT_LEVELS`, `RATIO_TAGS` |
| `components/ui/*` | — | — | ~45 stock shadcn/ui primitives; untouched, keep as-is |
| `lib/lovable-error-reporting.ts`, `error-capture.ts`, `error-page.ts` | — | — | No-op outside the Lovable editor (hooks exist only in editor preview). Remove during cleanup; third-party telemetry hooks have no place in a privileged legal app (ZDR convention 1) |

Stack: TanStack Start (React 19, Vite SSR, file-based routes), Tailwind v4,
shadcn/ui (Radix), dark theme only, `lucide-react` icons.

## 2. State Management & Data-Fetching Patterns

- **State:** per-route `useState` only. No global store (no zustand/redux/context
  state). All "state" is derived via `useMemo` over imported constants.
- **Data fetching:** none. TanStack Query is installed and the `QueryClient` is
  wired through router context — the intended fetch layer is provisioned but
  completely unused.
- **Routing/meta:** TanStack Router `createFileRoute` with per-route `head()`.
- **Conclusion:** the refactor has no legacy fetch code to unwind. The pattern
  to adopt is already scaffolded: TanStack Query hooks per screen, keyed and
  cacheable, replacing the constants imports 1:1.

## 3. UI Contracts vs Phase1-Design §3.5 (`QueryResponse`)

Design schema: `answer: str`, `citations: Citation[]` (`document_id`,
`case_title`, `citation`, `court_level`, `year`, `page_start`, `page_end`,
`paragraph_refs: list[str]`, `source_pdf_url`, `verified`), `refusal: bool`.

| Contract element | MVP status | Match |
|---|---|---|
| Citation card: case name, citation, court, year, `p. X`, `¶ Y`, "Verified against source PDF" badge | `SearchResult` card renders exactly this (design §3.4: "matching the Aetoes Ops Hub contract" — the MVP *is* that contract) | STRONG MATCH |
| Filter chips (court level, ratio decidendi) | Present, map to `court_level`, `ratio_decidendi` | MATCH |
| Year filter | Present in UI but unwired; maps to `year_from`/`year_to` | PARTIAL (dead UI) |
| Answer text with inline citations | ABSENT — MVP shows excerpts only, no `answer` rendering | GAP |
| Refusal state (`refusal: true`, §3.4: vsim < 0.78 → immediate refusal; fabricated citation → refusal, never shown to user) | ABSENT — no refusal UI exists anywhere | GAP |
| `source_pdf_url` link | ABSENT — shows filename text, not a link | GAP |
| `page_start`/`page_end` + `paragraph_refs: list[str]` | Single `page: number`, single `paragraph: string` | SHAPE MISMATCH (minor) |
| Vault A/B toggle | Not in `QueryRequest` — vault scoping is tenant/RLS-side; per-vault filtering needs a contract extension | OPEN QUESTION for owner |
| Red-Teamer screen | NO endpoint in Phase 1 design at all | OUT OF SCOPE for Phase 1 contract |
| Statutory Tracker screen | NO endpoint in Phase 1 design at all | OUT OF SCOPE for Phase 1 contract |

## 4. Refactor Plan (no backend work — that stays in apps/api per HANDOFF)

Principle: **keep every presentational component; replace every mock source with
a typed client for `POST /v1/query` and future `/v1/*` endpoints.** One commit
per step (HANDOFF rule 2). `.md` files stay uncommitted (owner rule).

**Step 1 — Repo integration & hygiene.**
Move `mvp-audit/` → `apps/web/` in the RedCase monorepo. Delete
`lib/lovable-error-reporting.ts`, `error-capture.ts`, `server.ts` Lovable
wrappers; keep error-page rendering but route reporting to our own logger.
Verify `npm run dev` serves and accepts `--host`/`--port` (Kimi Work preview
contract).

**Step 2 — Typed API layer (`apps/web/src/lib/api/`).**
- `client.ts`: thin fetch wrapper — base URL from `VITE_API_BASE_URL`, tenant
  header, JSON error normalization, no secrets in the bundle.
- `types.ts`: generated from the FastAPI app's OpenAPI
  (`openapi-typescript`), so frontend types can never drift from the §3.5
  schemas. Checked-in generated file, regenerated in CI.

**Step 3 — Vault Search wired to `POST /v1/query`.**
`useVaultSearch` TanStack Query mutation mapping UI filters → `QueryRequest`.
Card props remapped `Citation → SearchResult`-shaped presentational props (keep
the card JSX untouched). Add: `answer` rendering with citations, **refusal
state component** (new — §3.4 contract), `source_pdf_url` link on the Verified
badge, wire the dead Year filter. Delete `VAULT_RESULTS`.

**Step 4 — Red-Teamer & Tracker (typed clients, backend pending).**
Phase 1 design defines no endpoints for these screens. Build their typed
clients + interfaces in `lib/api/` against owner-confirmed contract shapes
(open question — see §5), with the same interface implemented by a typed
dev adapter so the approved UI stays fully functional until the FastAPI
endpoints land; swap the base URL, delete `BATTLE_CARD`/`DEADLINES` mocks.
Tracker's deadline computation moves server-side eventually; keep the local
calculator as a convenience preview.

**Step 5 — Cleanup.** Delete `lib/aetoes-data.ts`; document the screens-to-end
-point map in code comments; final DoD check per screen.

## 5. Open Questions for Owner (before Step 4)

1. Vault A/B toggle: add `vault` filter to `/v1/query` (contract extension
   beyond §3.5), or is vault selection resolved tenant-side? Design docs win —
   need the ruling recorded.
2. Red-Teamer and Tracker endpoint shapes: define now (preferred, so the
   typed clients are built once) or defer to Phase 2 design doc?
3. Auth model for the frontend→FastAPI path: API key header per tenant for
   Phase 1, or full login from day one?
