import { Eyebrow } from "./MarketingLayout";

export function Pricing() {
  return (
    <section id="pricing" className="border-y border-border/60 bg-surface/40">
      <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="max-w-2xl">
          <Eyebrow>Pricing</Eyebrow>
          <h2 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
            Simple tiers. Pricing on request.
          </h2>
        </div>

        <div className="mt-10 grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* CORE */}
          <div className="flex flex-col rounded-2xl border border-gold/30 bg-background/40 p-8">
            <div className="font-mono text-xs uppercase tracking-[0.24em] text-gold">
              Core
            </div>
            <h3 className="mt-3 font-display text-2xl font-semibold">
              Everything a firm runs on. Vaults, channels, research, deadlines,
              time &amp; invoicing, conflict checks.
            </h3>
            <a
              href="/onboarding"
              className="mt-8 inline-flex w-fit items-center justify-center rounded-lg border border-gold/40 px-6 py-3 text-sm font-semibold text-foreground transition-all duration-200 hover:bg-gold/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
            >
              Talk to us
            </a>
          </div>

          {/* WORKBENCH */}
          <div className="flex flex-col rounded-2xl border border-primary/30 bg-background/40 p-8">
            <div className="font-mono text-xs uppercase tracking-[0.24em] text-primary">
              Workbench
            </div>
            <h3 className="mt-3 font-display text-2xl font-semibold">
              Every lawyer&rsquo;s personal engine. All analysis packs, the Legal
              Assistant, saved searches.
            </h3>
            <a
              href="/onboarding"
              className="mt-8 inline-flex w-fit items-center justify-center rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground transition-all duration-200 hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
            >
              Talk to us
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
