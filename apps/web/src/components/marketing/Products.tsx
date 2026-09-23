// PRODUCTS band - the four product surfaces rendered as compact UI previews.
import { Search, Swords, MessageSquareText, Layers } from "lucide-react";
import { Eyebrow } from "./MarketingLayout";

export function Products() {
  return (
    <section className="border-y border-border/60 bg-surface/40">
      <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="text-center">
          <Eyebrow>The product</Eyebrow>
          <h2 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
            Four surfaces. One engine.
          </h2>
        </div>

        <div className="mt-12 grid grid-cols-1 gap-5 md:grid-cols-2">
          <VaultSearchCard />
          <RedTeamCard />
          <AssistantCard />
          <FirmOpsCard />
        </div>
      </div>
    </section>
  );
}

function VaultSearchCard() {
  return (
    <div className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-background/50 transition-all duration-200 hover:-translate-y-1 hover:border-gold/40 hover:shadow-elevated">
      <div className="flex items-center gap-2 border-b border-border/70 p-4 font-mono text-[9px] uppercase tracking-[0.2em] text-gold">
        <Search className="size-3.5" />
        Vault Search
      </div>
      <div className="flex-1 space-y-3 p-5">
        <div className="rounded-lg border border-gold/25 bg-background/60 p-3">
          <div className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
            Grounded answer
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-foreground/90">
            Preliminary objection &mdash; strategy &amp; the binding rule, cited
            page and paragraph.
          </p>
          <div className="mt-2 font-mono text-[10px] text-gold">
            (2008) 5 NWLR (Pt. 1080) 227 &middot; p.9
          </div>
        </div>
      </div>
    </div>
  );
}

function RedTeamCard() {
  return (
    <div className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-background/50 transition-all duration-200 hover:-translate-y-1 hover:border-gold/40 hover:shadow-elevated">
      <div className="flex items-center gap-2 border-b border-border/70 p-4 font-mono text-[9px] uppercase tracking-[0.2em] text-primary">
        <Swords className="size-3.5" />
        Red-Teamer
      </div>
      <div className="flex-1 space-y-3 p-5">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted-foreground">
            Opposing argument &middot; strength
          </span>
          <span className="font-mono text-xs text-foreground">7 / 10</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-border/60">
          <div className="h-full w-[70%] rounded-full bg-gradient-to-r from-gold to-primary" />
        </div>
      </div>
    </div>
  );
}

function AssistantCard() {
  return (
    <div className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-background/50 transition-all duration-200 hover:-translate-y-1 hover:border-gold/40 hover:shadow-elevated">
      <div className="flex items-center gap-2 border-b border-border/70 p-4 font-mono text-[9px] uppercase tracking-[0.2em] text-gold">
        <MessageSquareText className="size-3.5" />
        Legal Assistant
      </div>
      <div className="flex-1 space-y-3 p-5">
        <div className="rounded-lg rounded-br-sm border border-gold/25 bg-background/60 p-3">
          <p className="text-xs leading-relaxed text-foreground/90">
            Draft the reply on the objection, one section at a time?
          </p>
        </div>
      </div>
    </div>
  );
}

function FirmOpsCard() {
  return (
    <div className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-background/50 transition-all duration-200 hover:-translate-y-1 hover:border-gold/40 hover:shadow-elevated">
      <div className="flex items-center gap-2 border-b border-border/70 p-4 font-mono text-[9px] uppercase tracking-[0.2em] text-primary">
        <Layers className="size-3.5" />
        Firm Ops
      </div>
      <div className="flex-1 space-y-3 p-5">
        <div className="flex items-center justify-between rounded-md border border-border/70 bg-background/40 px-3 py-2">
          <span className="text-xs text-gold">Deadline filed</span>
          <span className="font-mono text-[10px] text-muted-foreground">3 days</span>
        </div>
        <div className="flex items-center justify-between rounded-md border border-border/70 bg-background/40 px-3 py-2">
          <span className="text-xs text-muted-foreground">Invoice #104</span>
          <span className="font-mono text-[10px] text-gold">Issued</span>
        </div>
      </div>
    </div>
  );
}
