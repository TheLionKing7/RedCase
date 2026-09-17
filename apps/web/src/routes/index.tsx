import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Search, FileText, Loader2, ShieldCheck, Database, Library } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import {
  COURT_LEVELS,
  RATIO_TAGS,
  VAULT_RESULTS,
  type Vault,
} from "@/lib/aetoes-data";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Vault Search — Aetoes Ops Hub" },
      {
        name: "description",
        content:
          "Dual-vault legal retrieval across Aetoes internal briefs and the Nigerian Juris OS, with verified PDF page citations.",
      },
      { property: "og:title", content: "Vault Search — Aetoes Ops Hub" },
      {
        property: "og:description",
        content:
          "Search internal briefs and Nigerian case law with page-pinned, hallucination-guarded citations.",
      },
    ],
  }),
  component: VaultSearch,
});

function VaultSearch() {
  const [vault, setVault] = useState<Vault>("B");
  const [query, setQuery] = useState("condition precedent jurisdiction originating process");
  const [court, setCourt] = useState<string>("All Courts");
  const [ratio, setRatio] = useState<string>("All Ratios");
  const [year, setYear] = useState("Any year");
  const [searching, setSearching] = useState(false);
  const [ran, setRan] = useState(true);

  const results = useMemo(
    () =>
      VAULT_RESULTS.filter((r) => r.vault === vault).filter(
        (r) => court === "All Courts" || r.court === court,
      ),
    [vault, court],
  );

  function run() {
    setSearching(true);
    setRan(false);
    setTimeout(() => {
      setSearching(false);
      setRan(true);
    }, 900);
  }

  return (
    <AppShell eyebrow="Dual-Vault Engine" title="Vault Search">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Vault toggle */}
        <div className="panel p-2">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <VaultTile
              active={vault === "A"}
              onClick={() => setVault("A")}
              icon={<Library className="size-4" />}
              label="Vault A"
              name="Internal Briefs"
              meta="1,284 documents · Aetoes-only, encrypted at rest"
              tone="gold"
            />
            <VaultTile
              active={vault === "B"}
              onClick={() => setVault("B")}
              icon={<Database className="size-4" />}
              label="Vault B"
              name="Nigerian Juris OS"
              meta="41,902 judgments · SC, CA, FHC, NICN"
              tone="cyan"
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
                className="w-full rounded-lg border border-input bg-background/60 py-3 pl-10 pr-4 text-sm outline-none transition-shadow placeholder:text-muted-foreground focus:glow-cyan"
              />
            </div>
            <button
              onClick={run}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-gold px-6 py-3 text-sm font-semibold text-gold-foreground transition-opacity hover:opacity-90"
            >
              {searching ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
              Run RAG Query
            </button>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Filter label="Court Level" value={court} onChange={setCourt} options={COURT_LEVELS} />
            <Filter
              label="Year"
              value={year}
              onChange={setYear}
              options={["Any year", "2020–2026", "2010–2019", "2000–2009", "Pre-2000"]}
            />
            <Filter label="Ratio Decidendi" value={ratio} onChange={setRatio} options={RATIO_TAGS} />
          </div>
        </div>

        {/* Results */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="font-mono uppercase tracking-widest">
            {searching ? "Retrieving…" : `${results.length} passages · re-ranked`}
          </span>
          <span className="inline-flex items-center gap-1.5 text-success">
            <ShieldCheck className="size-3.5" /> Citation guard active — every answer page-pinned
          </span>
        </div>

        <div className="space-y-4">
          {searching &&
            [0, 1, 2].map((i) => (
              <div key={i} className="panel h-36 animate-pulse opacity-60" />
            ))}

          {ran &&
            !searching &&
            results.map((r) => (
              <article key={r.id} className="panel p-5 transition-colors hover:border-gold/40">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold">{r.title}</h2>
                    <p className="mt-0.5 font-mono text-xs text-gold">{r.citation}</p>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-xs text-cyan">
                      {(r.confidence * 100).toFixed(0)}% match
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {r.court} · {r.year}
                    </div>
                  </div>
                </div>

                <p className="mt-3 border-l-2 border-cyan/50 pl-4 text-sm leading-relaxed text-foreground/90">
                  “{r.excerpt}”
                </p>

                <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px]">
                  <span className="rounded-full bg-muted px-2.5 py-1 text-muted-foreground">
                    Ratio: {r.ratio}
                  </span>
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-gold/40 px-2.5 py-1 font-mono text-gold">
                    <FileText className="size-3" />
                    {r.source} · p.{r.page} · {r.paragraph}
                  </span>
                  <span className="inline-flex items-center gap-1 text-success">
                    <ShieldCheck className="size-3" /> Verified against source PDF
                  </span>
                </div>
              </article>
            ))}
        </div>
      </div>
    </AppShell>
  );
}

function VaultTile({
  active,
  onClick,
  icon,
  label,
  name,
  meta,
  tone,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  name: string;
  meta: string;
  tone: "gold" | "cyan";
}) {
  const activeRing = tone === "gold" ? "glow-gold" : "glow-cyan";
  const accent = tone === "gold" ? "text-gold" : "text-cyan";
  return (
    <button
      onClick={onClick}
      className={`rounded-lg px-5 py-4 text-left transition-all ${
        active ? `bg-surface-raised ${activeRing}` : "bg-transparent opacity-60 hover:opacity-100"
      }`}
    >
      <div className={`flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] ${accent}`}>
        {icon}
        {label}
        {active && <span className="ml-auto rounded-full bg-success/15 px-2 py-0.5 text-success">ACTIVE</span>}
      </div>
      <div className="mt-2 text-base font-semibold">{name}</div>
      <div className="mt-1 text-[11px] text-muted-foreground">{meta}</div>
    </button>
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
  options: readonly string[];
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
          <option key={o} value={o} className="bg-surface">
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}
