import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  Search,
  FileText,
  Loader2,
  ShieldCheck,
  ShieldAlert,
  ArrowUpRight,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { CoachMarks } from "@/components/CoachMarks";
import { useVaultQuery } from "@/lib/api/query";
import { ApiError } from "@/lib/api/client";
import type { Citation } from "@/lib/api/types";
import { COURT_LEVELS, RATIO_TAGS } from "@/lib/court-filters";
import type { FilterOption } from "@/lib/court-filters";

export const Route = createFileRoute("/_authed/search")({
  head: () => ({
    meta: [
      { title: "Vault Search â€” RedCase" },
      {
        name: "description",
        content:
          "Dual-vault legal retrieval across Aetoes internal briefs and the Nigerian Juris OS, with verified PDF page citations.",
      },
      { property: "og:title", content: "Vault Search â€” RedCase" },
      {
        property: "og:description",
        content:
          "Search internal briefs and Nigerian case law with page-pinned, hallucination-guarded citations.",
      },
    ],
  }),
  component: SearchPage,
});

// Owner ruling 1 (2026-09-16): no /v1/query vault param â€” Phase 1 is locked to
// Vault B (Nigerian Juris OS); Vault A renders disabled with a PHASE 2 tag.
// Phase 2 moves vault selection server-side and replaces the toggle with
// per-citation vault badges (Phase2 Â§2.2).

// UI year ranges â†’ QueryRequest year_from/year_to (Phase1-Design Â§3.5).
function yearRange(label: string): { year_from?: number; year_to?: number } {
  switch (label) {
    case "2020â€“2026":
      return { year_from: 2020, year_to: 2026 };
    case "2010â€“2019":
      return { year_from: 2010, year_to: 2019 };
    case "2000â€“2009":
      return { year_from: 2000, year_to: 2009 };
    case "Pre-2000":
      return { year_to: 1999 };
    default:
      return {};
  }
}

// Â§2.1 CHECK enums â†’ law-report court abbreviations (how counsel cites them).
const COURT_BADGE: Record<string, string> = {
  SUPREME_COURT: "SC",
  COURT_OF_APPEAL: "CA",
  FEDERAL_HIGH_COURT: "FHC",
  STATE_HIGH_COURT: "SHC",
  NICN: "NICN",
  STATUTE: "STAT",
};

function SearchPage() {
  const [query, setQuery] = useState(
    "condition precedent jurisdiction originating process",
  );
  const [court, setCourt] = useState<string>(""); // "" = All Courts (no filter)
  const [ratio, setRatio] = useState<string>(""); // "" = All Ratios (no filter)
  const [year, setYear] = useState("Any year");
  const [hasRun, setHasRun] = useState(false);

  const vaultQuery = useVaultQuery();
  const data = vaultQuery.data;
  const questionValid = query.trim().length >= 10; // Â§3.5 min_length=10

  function run() {
    if (!questionValid || vaultQuery.isPending) return;
    setHasRun(true);
    vaultQuery.mutate({
      question: query.trim(),
      court_level: court || null,
      ratio_decidendi: ratio || null,
      ...yearRange(year),
    });
  }

  return (
    <AppShell eyebrow="Nigerian Juris OS" title="Vault Search">
      <CoachMarks
        surface="search"
        icon={Search}
        steps={[
          {
            title: "Run your first vault search",
            body: "Ask a legal question in plain language and press Run Query. RedCase searches internal briefs and Nigerian case law in one pass.",
          },
          {
            title: "Every answer is page-pinned",
            body: "Results carry verified PDF citations. The citation guard blocks ungrounded answers — cannot rely on anything that isn't sourced.",
          },
          {
            title: "Narrow by court and year",
            body: "Use the Court Level and Year filters to focus results the way you'd cite them — from full court to trial, and across reporting decades.",
          },
        ]}
      />
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Vault scope â€” Phase 1 locked to Vault B (owner ruling 1). */}
        <VaultScopeBar />

        {/* Command bar */}
        <div className="panel p-5">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && run()}
                placeholder="State the issue â€” e.g. what test governsâ€¦"
                className="w-full rounded-lg border border-input bg-background/60 py-3 pl-10 pr-4 text-sm outline-none transition-shadow placeholder:text-muted-foreground focus:glow-steel"
              />
            </div>
            <button
              onClick={run}
              disabled={!questionValid || vaultQuery.isPending}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {vaultQuery.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Search className="size-4" />
              )}
              Run Query
            </button>
          </div>
          {!questionValid && (
            <p className="mt-2 text-[11px] text-muted-foreground">
              Questions need at least 10 characters (API contract, Phase1-Design
              Â§3.5).
            </p>
          )}

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Filter
              label="Court Level"
              value={court}
              onChange={setCourt}
              options={COURT_LEVELS}
            />
            <Filter
              label="Year"
              value={year}
              onChange={setYear}
              options={[
                { label: "Any year", value: "Any year" },
                { label: "2020â€“2026", value: "2020â€“2026" },
                { label: "2010â€“2019", value: "2010â€“2019" },
                { label: "2000â€“2009", value: "2000â€“2009" },
                { label: "Pre-2000", value: "Pre-2000" },
              ]}
            />
            <Filter
              label="Ratio Decidendi"
              value={ratio}
              onChange={setRatio}
              options={RATIO_TAGS}
            />
          </div>
        </div>

        {/* Results */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="font-mono uppercase tracking-widest">
            {vaultQuery.isPending
              ? "Retrievingâ€¦"
              : data && !data.refusal
                ? `${data.citations.length} authorit${data.citations.length === 1 ? "y" : "ies"} Â· verified`
                : "Awaiting query"}
          </span>
          <span className="inline-flex items-center gap-1.5 text-success">
            <ShieldCheck className="size-3.5" /> Citation guard active â€” every
            answer page-pinned
          </span>
        </div>

        {vaultQuery.isPending && (
          <div className="space-y-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="panel h-36 animate-pulse opacity-60" />
            ))}
          </div>
        )}

        {vaultQuery.isError && <QueryErrorState error={vaultQuery.error} />}

        {data?.refusal && <RefusalPanel />}

        {data && !data.refusal && (
          <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-[1fr_360px]">
            <AnswerOpinion answer={data.answer} count={data.citations.length} />
            <AuthoritiesRail citations={data.citations} />
          </div>
        )}

        {!hasRun && !vaultQuery.isPending && (
          <div className="panel p-10 text-center">
            <p className="font-display text-xl text-foreground/90">
              The Intelligent Engine for Modern Law
            </p>
            <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
              State an issue to retrieve grounded, page-pinned authority from
              the Nigerian Juris OS â€” or run the example above. Every answer
              is verified against the source or refused outright.
            </p>
          </div>
        )}
      </div>
    </AppShell>
  );
}

/** Phase 1 vault scope: a segmented control, not two hero tiles. Vault
 *  selection is server-side by ruling; the pills state the contract plainly. */
function VaultScopeBar() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="inline-flex rounded-lg border border-border bg-surface p-1">
        <span className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground">
          Vault B Â· Nigerian Juris OS
        </span>
        <span
          className="inline-flex cursor-not-allowed items-center gap-2 rounded-md px-4 py-2 text-sm text-muted-foreground/50"
          title="Vault A joins the corpus server-side in Phase 2"
        >
          Vault A Â· Internal Briefs
          <span className="rounded-full bg-muted px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest text-muted-foreground">
            Phase 2
          </span>
        </span>
      </div>
      <p className="text-[11px] text-muted-foreground">
        41,902 judgments Â· SC, CA, FHC, SHC, NICN â€” Vault A matter scoping
        arrives server-side in Phase 2.
      </p>
    </div>
  );
}

/** The grounded answer, set like an opinion excerpt: display serif for the
 *  narrative, mono for the audit line. Rendered only when every citation
 *  verified (Â§3.4). */
function AnswerOpinion({ answer, count }: { answer: string; count: number }) {
  return (
    <section className="panel p-6 lg:p-8">
      <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-steel">
        Grounded Answer
      </div>
      <p className="mt-4 font-display text-lg leading-8 text-foreground/95 whitespace-pre-wrap">
        {answer}
      </p>
      <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-4 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5 text-success">
          <ShieldCheck className="size-3" /> Verified against retrieved passages
        </span>
        <span>
          {count} {count === 1 ? "authority" : "authorities"} pinned
        </span>
        <span>Question audit-hashed Â· ZDR</span>
      </div>
    </section>
  );
}

/**
 * Refusal â€” Â§3.4 contract verbatim. Below the 0.78 gate or on citation-
 * integrity failure, no answer is rendered and no fabricated citation is
 * ever shown. The refusal is the product's honesty, so it carries the
 * crimson seal and the contract's own words.
 */
function RefusalPanel() {
  return (
    <section className="panel border-l-4 border-l-primary p-8">
      <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-primary">
        Refused Â· citation integrity
      </div>
      <h2 className="mt-3 font-display text-2xl leading-snug">
        â€œNo binding precedent found in Vault B.â€
      </h2>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted-foreground">
        The retrieved passages did not meet the verification gate for this
        question. Under the citation-integrity contract, RedCase shows no answer
        rather than an unverified one â€” a fabricated citation is never
        displayed.
      </p>
      <p className="mt-3 text-[11px] text-muted-foreground">
        Broaden the court-level or year filters, or restate the issue with more
        specific terms of art.
      </p>
    </section>
  );
}

/** Table of Authorities â€” briefs list authorities; so does RedCase. Each row
 *  is a law-report citation line: court badge, NWLR cite, pinpoint pages and
 *  paragraph refs, and the seal linking the stored source PDF. */
function AuthoritiesRail({ citations }: { citations: Citation[] }) {
  return (
    <aside className="space-y-3 lg:sticky lg:top-28">
      <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
        Table of Authorities Â· {citations.length}
      </div>
      {citations.map((c) => (
        <AuthorityRow key={c.document_id} citation={c} />
      ))}
    </aside>
  );
}

function AuthorityRow({ citation: c }: { citation: Citation }) {
  const pages =
    c.page_start === c.page_end
      ? `p. ${c.page_start}`
      : `pp. ${c.page_start}â€“${c.page_end}`;
  const paras = c.paragraph_refs.length
    ? ` Â· Â¶ ${c.paragraph_refs.join(", Â¶ ")}`
    : "";
  return (
    <article className="panel border-l-2 border-l-gold/60 p-4 transition-colors hover:border-l-gold">
      <div className="flex items-center gap-2">
        <span className="rounded border border-gold/40 bg-gold/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-wider text-gold">
          {COURT_BADGE[c.court_level] ?? c.court_level}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground">
          {c.year}
        </span>
        {c.verified ? (
          <span className="ml-auto inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider text-success">
            <ShieldCheck className="size-3" /> Verified
          </span>
        ) : (
          <span className="ml-auto inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider text-warning">
            <ShieldAlert className="size-3" /> Unverified
          </span>
        )}
      </div>
      <h3 className="mt-2 font-display text-base leading-snug">
        {c.case_title}
      </h3>
      <p className="mt-1 font-mono text-xs text-gold">{c.citation}</p>
      <p className="mt-1.5 font-mono text-[11px] text-muted-foreground">
        <FileText className="mr-1 inline size-3" />
        {pages}
        {paras}
      </p>
      <a
        href={c.source_pdf_url}
        target="_blank"
        rel="noreferrer"
        className="mt-2 inline-flex items-center gap-1 text-xs text-foreground/80 underline-offset-2 hover:text-gold hover:underline"
      >
        Source PDF <ArrowUpRight className="size-3" />
      </a>
    </article>
  );
}

function QueryErrorState({ error }: { error: unknown }) {
  const auth = error instanceof ApiError && error.isAuthError;
  return (
    <section className="panel border-destructive/40 p-6">
      <h2 className="flex items-center gap-2 text-base font-semibold text-destructive">
        <ShieldAlert className="size-4" />
        {auth ? "Sign-in required" : "Query failed"}
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {auth
          ? "Your Supabase session is missing or expired. Sign in again with the email magic link."
          : error instanceof Error
            ? error.message
            : "Unknown error â€” is the FastAPI backend running?"}
      </p>
    </section>
  );
}

function Filter({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: readonly FilterOption[];
}) {
  return (
    <label className="block">
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 w-full rounded-lg border border-input bg-background/60 px-3 py-2.5 text-sm outline-none focus:border-gold"
      >
        {options.map((o) => (
          <option key={o.label} value={o.value} className="bg-surface">
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
