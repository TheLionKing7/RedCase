# RedCase Design System — Principles & Guidelines

*Synthesized 2026-09-17 from: HANDOFF.md §2 (six global conventions), docs/RC-BrandTheme.md, Phase1/2/3 design-doc UI contracts (§3.4, §3.5, §1.2, §3.1), owner rulings (2026-09-16/17), and the Vault Search redesign rationale (commit 3472f99). Where sources conflict, the order of authority is: design docs > this document > the MVP UI conventions.*

---

## 0. Frame — what RedCase is (and is not)

**RedCase is a multi-tenant legal intelligence platform.** Aetoes Legal is tenant zero — the first firm on the platform — and its operational flow *guides* the design. The product is never framed as "a tool for Aetoes"; Aetoes appears only as tenant context (sidebar: "Aetoes Legal · Tenant Zero").

- Tagline: **"The Intelligent Engine for Modern Law."**
- Positioning: a **command engine, not a file cabinet** — dense, keyboard-first, telemetry-literate. It "doesn't ask permission"; it states what it verified and what it refused.
- The unit of work is the **case**; the unit of trust is the **citation**.

---

## 1. Principles

### P1 — Citations are the product
Every legal proposition the UI renders must be traceable to a page-pinned, verified source. A citation is never decoration: the VERIFIED seal, the pinpoint pins (`pp. X–Y · ¶ N`), and the source-PDF link are the contract made visible. If a screen cannot show its authority, it does not ship.
*Source: Phase1 §3.4; HANDOFF convention 4 (citation verification).*

### P2 — Refusal is a first-class state
"No binding precedent found in Vault B." is the product's honesty, not an error. Refusals get the same design care as answers: Crimson Signal seal, the contract's own words, and guidance to restate the issue. Never render an unverified answer; never show a fabricated citation.
*Source: Phase1 §3.4; owner-approved deferred-embed refusal path.*

### P3 — Brand tokens are law
Crimson `#D0021B`, Obsidian `#0F1115`, Vellum Gold `#E2C044` are used exactly; no invented hues, no "close enough" substitutes. The brand palette defines no cool accent — secondary accents use a **steel** tint of the obsidian family (`#8E99A8`). Functional semantics (success/warning/destructive) are allowed off-palette because they must stay distinct from brand signals.
*Source: HANDOFF convention 6; RC-BrandTheme.md.*

### P4 — Legal vernacular is the UI language
The interface speaks like counsel writes: law-report citations in NWLR form, court badges (`SC`, `CA`, `FHC`, `SHC`, `NICN`), *ratio decidendi*, *coram*, pinpoint `¶` references, **Table of Authorities**. Structure encodes real legal information — a court badge is not a colored dot, it is how a lawyer cites. Copy names what lawyers control and recognize ("State the issue", "broaden the court-level filter").
*Source: frontend-design skill (structure is information); redesign commit 3472f99.*

### P5 — One bold thing per screen
Every screen has a single signature element; everything around it is quiet. Vault Search's signature is the opinion + Table of Authorities. Crimson is spent on primary actions and the active vault — not sprinkled. If a new element competes with the signature, cut it (Chanel's mirror rule).
*Source: frontend-design skill (spend boldness in one place).*

### P6 — Multi-tenant from day one, invisible in the chrome
Tenant scoping lives server-side (RLS, JWT claims). The UI never leaks tenancy mechanics — no tenant switchers, no "your instance" copy. Vault A/B selection is **server-side** (owner ruling 1); Vault A renders disabled with a PHASE 2 tag rather than a fake control. Phase 2 replaces the toggle with per-citation vault badges (Phase2 §2.2).
*Source: HANDOFF convention 5; owner ruling 1.*

### P7 — Auditable by design, private by default (ZDR)
The UI may surface *that* something is audited ("question audit-hashed · ZDR") but never raw question bodies, document text, or secrets in logs or telemetry. Latency/telemetry claims in the UI must reflect real API fields — never invent numbers for effect.
*Source: HANDOFF convention 1 (ZDR), convention 3 (audit immutability).*

### P8 — Failure and emptiness direct, they don't apologize
Errors state what happened and how to fix it in the product's voice ("Sign-in required — your magic link session expired"). Empty screens invite the next action and may carry the tagline. Loading states show skeletons of the real layout, not spinners.
*Source: frontend-design skill (copy as design material).*

### P9 — Accessibility is the floor, not a feature
Keyboard-focusable everything with visible focus rings (gold), `prefers-reduced-motion` respected, responsive down to mobile (authorities rail stacks under the answer), contrast ≥ 4.5:1 on text.
*Source: frontend-design skill (quality floor).*

---

## 2. Tokens

| Token | Value | Role |
|---|---|---|
| `--background` | `#0F1115` | Obsidian page chrome |
| `--surface` / `--surface-raised` | `#15181D` / `#1A1D23` | Panels, cards |
| `--foreground` | `#ECEDF0` | Primary text on obsidian |
| `--muted-foreground` | `#9BA1AB` | Captions, eyebrows, meta |
| `--border` / `--input` | `#2A2F38` | Hairlines, form edges |
| `--primary` | `#D0021B` | Crimson Signal — primary actions, active vault, refusal seal, chart accents |
| `--primary-foreground` | `#FFFFFF` | On crimson |
| `--gold` | `#E2C044` | Vellum Gold — citations, pins, badges, focus ring, nav active indicator |
| `--gold-foreground` | `#0F1115` | On vellum |
| `--steel` | `#8E99A8` | Secondary accent (replaces the retired cyan) |
| `--success` / `--warning` / `--destructive` | `#3ECF8E` / `#E2A336` / `#E5484D` | Functional only — never brand decoration |

Derived: `--gradient-gold` (`#C9A832 → #EED67A`), `--gradient-vault` (radial `#1A1F2A → #0F1115`), `--glow-gold`, `--glow-steel`, `--shadow-elevated`. Dark-mode only; there is no light theme in Phase 1.

**Logo**: Balanced Neural Scale mark (geometry variant, text-free) from `docs/RedCaseSVG/`, served from `public/brand/`; white monochrome on obsidian chrome, full-color (crimson) for favicon/general use, black only on light surfaces. Wordmark: "Red" bold + "Case" light, never re-set in another face.

---

## 3. Typography

| Role | Face | Used for |
|---|---|---|
| Display / opinion | Playfair Display | Page titles (h1), case names, the grounded-answer narrative, tagline moments |
| UI / body | Inter Tight | Controls, labels, descriptions, data tables |
| Mono / record | JetBrains Mono | Citations, pinpoint pins, court badges, eyebrows, telemetry/audit lines, uppercase tracking labels |

Rules: legal narrative and case names get the display serif (gravitas of the profession); anything that is a *record* — a citation, a pin, an audit hash — is always mono. Eyebrows are mono, uppercase, ≥ 0.18em tracking, muted-foreground.

---

## 4. Patterns & components

- **Command bar** — one input + one crimson primary action; filters sit beneath as enum-backed selects (wire values are the §2.1 CHECK enums, never display strings).
- **Vault scope** — segmented control; active vault in Crimson Signal, inactive vault disabled with a PHASE 2 chip; one sentence states the server-side contract.
- **Grounded answer (opinion panel)** — display-serif narrative + mono audit line; rendered only when every citation verified.
- **Table of Authorities** — sticky rail (top on mobile) of authority rows: court badge · year · case name (display) · NWLR citation (gold mono) · `pp. X–Y · ¶ N` pins · VERIFIED seal · Source PDF link. Left gold border is the pin motif.
- **Refusal panel** — crimson left seal, eyebrow "Refused · citation integrity", contract sentence verbatim in quotes, explanation, restatement guidance.
- **Filter chips / selects** — labels mono uppercase; "All …" option value is `""` → `null` on the wire.
- **Status rail (sidebar footer)** — green presence dots + mono labels + build tag + tagline. Presence claims must mirror real corpus stats when wired.

## 5. Copy guidelines

Sentence case; active voice; controls say exactly what they do ("Run Query"). The refusal sentence and citation format strings are **frozen contract copy** — change only with a design-doc amendment and battery re-run. Numbers/spacing: spaces between values and units. No apology copy; no cleverness in legal-record surfaces.

## 6. Governance

1. New screens derive from these principles; deviations need a recorded conflict (HANDOFF rule 3) in the commit message.
2. Wire shapes are owned by the design docs (§3.5 QueryResponse, §1.2 Battle Card, §3.1 deadline_events) — the TypeScript types in `src/lib/api/` are verbatim mirrors; drift is a defect.
3. Mock data is prohibited in committed code; development uses the typed dev adapters gated on `VITE_API_DEV_ADAPTER=1`.
4. Prompt/grounding copy (`GROUNDED_SYSTEM`) is contract text — rewording requires the 50-question battery re-run.
5. Every visual change is verified by screenshot before commit (headless Chrome is sufficient) and must keep typecheck + eslint + build green.
