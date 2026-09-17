import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  Search,
  FileText,
  Loader2,
  ShieldCheck,
  ShieldAlert,
  Database,
  Library,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useVaultQuery } from "@/lib/api/query";
import { ApiError } from "@/lib/api/client";
import type { Citation } from "@/lib/api/types";
import { COURT_LEVELS, RATIO_TAGS } from "@/lib/court-filters";
import type { FilterOption } from "@/lib/court-filters";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Vault Search — RedCase" },
      {
        name: "description",
        content:
          "Dual-vault legal retrieval across Aetoes internal briefs and the Nigerian Juris OS, with verified PDF page citations.",
      },
      { property: "og:title", content: "Vault Search — RedCase" },
      {
        property: "og:description",
        content:
          "Search internal briefs and Nigerian case law with page-pinned, hallucination-guarded citations.",
      },
    ],
  }),
  component: VaultSearch,
});

// Owner ruling 1 (2026-09-16): no /v1/query vault param — Phase 1 is locked to
// Vault B (Nigerian Juris OS); the Vault A tile renders disabled with a
// PHASE 2 tag below. Phase 2 moves vault selection server-side and replaces
// the toggle with per-citation vault badges (Phase2 §2.2).

// UI year ranges → QueryRequest year_from/year_to (Phase1-Design §3.5).
function yearRange(label: string): { year_from?: number; year_to?: number } {
  switch (label) {
    case "2020–2026":
      return { year_from: 2020, year_to: 2026 };
    case "2010–2019":
      return { year_from: 2010, year_to: 2019 };
    case "2000–2009":
      return { year_from: 2000, year_to: 2009 };
    case "Pre-2000":
      return { year_to: 1999 };
    default:
      return {};
  }
}

function VaultSearch() {
  const [query, setQuery] = useState(
    "condition precedent jurisdiction originating process",
  );
  const [court, setCourt] = useState<string>(""); // "" = All Courts (no filter)
  const [ratio, setRatio] = useState<string>(""); // "" = All Ratios (no filter)
  const [year, setYear] = useState("Any year");
  const [hasRun, setHasRun] = useState(false);

  const vaultQuery = useVaultQuery();
  const data = vaultQuery.data;
  const questionValid = query.trim().length >= 10; // §3.5 min_length=10

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
    <AppShell eyebrow="Dual-Vault Engine" title="Vault Search">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Vault scope — Phase 1: locked to Vault B (owner ruling 1). */}
        <div className="panel p-2">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <VaultTile
              active={false}
              disabled
              icon={<Library className="size-4" />}
              label="Vault A"
              name="Internal Briefs"
              meta="Phase 2 — internal briefs join the corpus server-side"
              tag="PHASE 2"
              tone="gold"
            />
            <VaultTile
              active
              icon={<Database className="size-4" />}
              label="Vault B"
              name="Nigerian Juris OS"
              meta="41,902 judgments · SC, CA, FHC, NICN"
              tag="ACTIVE"
              tone="steel"
            />
          </div>
        </div>

        {/* Query bar */}
        <div className="panel p-5">
          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && run()}
                placeholder="Ask a question or paste an issue statement…"
                className="w-full rounded-lg border border-input bg-background/60 py-3 pl-10 pr-4 text-sm outline-none transition-shadow placeholder:text-muted-foreground focus:glow-steel"
              />
            </div>
            <button
              onClick={run}
              disabled={!questionValid || vaultQuery.isPending}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-gold px-6 py-3 text-sm font-semibold text-gold-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {vaultQuery.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Search className="size-4" />
              )}
              Run RAG Query
            </button>
          </div>
          {!questionValid && (
            <p className="mt-2 text-[11px] text-muted-foreground">
              Questions need at least 10 characters (API contract, Phase1-Design
              §3.5).
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
                { label: "2020–2026", value: "2020–2026" },
                { label: "2010–2019", value: "2010–2019" },
                { label: "2000–2009", value: "2000–2009" },
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
              ? "Retrieving…"
              : data
                ? `${data.citations.length} citations · re-ranked`
                : "Awaiting query"}
          </span>
          <span className="inline-flex items-center gap-1.5 text-success">
            <ShieldCheck className="size-3.5" /> Citation guard active — every
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

        {data?.refusal && <RefusalState />}

        {data && !data.refusal && (
          <>
            <AnswerPanel answer={data.answer} />
            <div className="space-y-4">
              {data.citations.map((c) => (
                <CitationCard key={c.document_id} citation={c} />
              ))}
            </div>
          </>
        )}

        {!hasRun && !vaultQuery.isPending && (
          <div className="panel p-10 text-center text-sm text-muted-foreground">
            Run a query to retrieve grounded, page-pinned authority from the
            Nigerian Juris OS.
          </div>
        )}
      </div>
    </AppShell>
  );
}

/** Grounded answer — §3.4: rendered only when every citation verified. */
function AnswerPanel({ answer }: { answer: string }) {
  return (
    <section className="panel glow-steel p-6">
      <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-steel">
        Grounded Answer
      </div>
      <p className="mt-3 text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">
        {answer}
      </p>
    </section>
  );
}

/**
 * Refusal state — §3.4 contract: best retrieved vsim below VECTOR_GATE (0.78)
 * or citation-integrity failure means NO answer is rendered, and a fabricated
 * citation is never shown to the user.
 */
function RefusalState() {
  return (
    <section className="panel border-gold/40 p-8 text-center">
      <ShieldAlert className="mx-auto size-8 text-gold" />
      <h2 className="mt-3 text-lg font-semibold">
        No verified authority found
      </h2>
      <p className="mx-auto mt-2 max-w-xl text-sm text-muted-foreground">
        RedCase could not ground an answer to this question in the retrieved
        corpus at the required confidence threshold. Under the
        citation-integrity contract, no answer is shown rather than an
        unverified one.
      </p>
      <p className="mt-3 text-[11px] text-muted-foreground">
        Tip: broaden the court-level or year filters, or rephrase the issue.
      </p>
    </section>
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
            : "Unknown error — is the FastAPI backend running?"}
      </p>
    </section>
  );
}

/** Citation card — the §3.4 rendering contract: case name, citation, court,
 *  year, p. X–Y, ¶ refs, "Verified against source PDF" linking the stored PDF. */
function CitationCard({ citation: c }: { citation: Citation }) {
  const pages =
    c.page_start === c.page_end
      ? `p. ${c.page_start}`
      : `p. ${c.page_start}–${c.page_end}`;
  return (
    <article className="panel p-5 transition-colors hover:border-gold/40">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{c.case_title}</h2>
          <p className="mt-0.5 font-mono text-xs text-gold">{c.citation}</p>
        </div>
        <div className="text-right">
          <div className="text-[11px] text-muted-foreground">
            {c.court_level} · {c.year}
          </div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px]">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-gold/40 px-2.5 py-1 font-mono text-gold">
          <FileText className="size-3" />
          {pages} · {c.paragraph_refs.join(", ")}
        </span>
        {c.verified ? (
          <a
            href={c.source_pdf_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-success underline-offset-2 hover:underline"
          >
            <ShieldCheck className="size-3" /> Verified against source PDF
          </a>
        ) : (
          <span className="inline-flex items-center gap-1 text-warning">
            <ShieldAlert className="size-3" /> Unverified — treat with caution
          </span>
        )}
      </div>
    </article>
  );
}

function VaultTile({
  active,
  disabled,
  icon,
  label,
  name,
  meta,
  tag,
  tone,
}: {
  active: boolean;
  disabled?: boolean;
  icon: React.ReactNode;
  label: string;
  name: string;
  meta: string;
  tag: string;
  tone: "gold" | "steel";
}) {
  const activeRing = tone === "gold" ? "glow-gold" : "glow-steel";
  const accent = tone === "gold" ? "text-gold" : "text-steel";
  return (
    <div
      aria-disabled={disabled || undefined}
      className={`rounded-lg px-5 py-4 text-left transition-all ${
        disabled
          ? "cursor-not-allowed opacity-50"
          : active
            ? `bg-surface-raised ${activeRing}`
            : "bg-transparent opacity-60 hover:opacity-100"
      }`}
    >
      <div
        className={`flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] ${accent}`}
      >
        {icon}
        {label}
        {active && (
          <span className="ml-auto rounded-full bg-success/15 px-2 py-0.5 text-success">
            {tag}
          </span>
        )}
        {disabled && (
          <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-muted-foreground">
            {tag}
          </span>
        )}
      </div>
      <div className="mt-2 text-base font-semibold">{name}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{meta}</div>
    </div>
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
