import { Eyebrow } from "./MarketingLayout";

export function DualVault() {
  return (
    <section id="product" className="border-y border-border/60 bg-surface/40">
      <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="max-w-3xl">
          <Eyebrow>Dual vault</Eyebrow>
          <h2 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
            Two vaults. One synthesis.
          </h2>
        </div>

        <div className="mt-10 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div className="rounded-xl border border-gold/25 bg-background/40 p-7">
            <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-gold">
              Vault A
            </div>
            <h3 className="mt-3 font-display text-xl font-semibold">
              Every brief, pleading and opinion your firm has written &mdash;
              encrypted, permissioned, and searchable by meaning.
            </h3>
          </div>
          <div className="rounded-xl border border-primary/30 bg-background/40 p-7">
            <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-primary">
              Vault B
            </div>
            <h3 className="mt-3 font-display text-xl font-semibold">
              Nigerian jurisprudence indexed by ratio decidendi &mdash; Supreme Court
              to NICN, cited to page and paragraph.
            </h3>
          </div>
        </div>

        <div className="mt-8 rounded-xl border border-border bg-gradient-to-br from-[#1a1f2a] to-[#0f1115] p-7">
          <div className="font-mono text-[11px] uppercase tracking-[0.24em] text-gold">
            Synthesis
          </div>
          <p className="mt-4 max-w-3xl font-display text-lg leading-8 text-foreground/90 sm:text-xl">
            Ask across both: &ldquo;How do we usually run a preliminary objection
            &mdash; and what does binding authority say?&rdquo; RedCase answers
            with your strategy and the law, separately cited.
          </p>
        </div>
      </div>
    </section>
  );
}
