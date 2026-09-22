import { useEffect, useState } from "react";
import { ArrowDown, ShieldCheck } from "lucide-react";
import { Eyebrow } from "./MarketingLayout";
import { SplitVaultVisual } from "./SplitVault";

const PROOF_CHIPS = [
  "0 fabricated citations across 50-question adversarial testing",
  "NDPA-ready · zero-retention AI",
  "AES-256 vault encryption",
];

export function Hero() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setReady(true), 420);
    return () => clearTimeout(t);
  }, []);

  return (
    <section className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#1a1f2a]/60 via-transparent to-transparent" />

      <div className="relative mx-auto max-w-7xl px-5 pb-20 pt-16 lg:px-8 lg:pb-28 lg:pt-24">
        <div className="text-center">
          <Eyebrow>The Legal Operating System · Nigeria First</Eyebrow>
          <h1 className="mx-auto mt-6 max-w-4xl font-display text-4xl font-semibold leading-[1.08] sm:text-5xl lg:text-6xl">
            Your firm&rsquo;s brain. Nigeria&rsquo;s law.{" "}
            <span className="text-gradient-gold">One engine.</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-muted-foreground sm:text-lg">
            RedCase unites your firm&rsquo;s knowledge and the country&rsquo;s
            jurisprudence in two secure vaults &mdash; and answers with pinpoint
            citations to real authority. Never invented. Always page-pinned.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <a
              href="/signin"
              className="inline-flex items-center justify-center rounded-lg bg-primary px-6 py-3 text-sm font-semibold text-primary-foreground shadow-sm transition-all duration-200 hover:bg-primary/90 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
            >
              Start your firm
            </a>
            <a
              href="#how"
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-surface px-6 py-3 text-sm font-semibold text-foreground transition-all duration-200 hover:border-gold/50 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
            >
              Watch how it works
              <ArrowDown className="size-4 text-gold" />
            </a>
          </div>
        </div>

        <div className="mx-auto mt-10 flex max-w-3xl flex-wrap items-center justify-center gap-3">
          {PROOF_CHIPS.map((chip) => (
            <span
              key={chip}
              className="inline-flex items-center gap-2 rounded-full border border-gold/25 bg-gold/5 px-4 py-1.5 text-xs text-foreground/85"
            >
              <ShieldCheck className="size-3.5 text-gold" />
              {chip}
            </span>
          ))}
        </div>

        <div id="how" className="relative mx-auto mt-16 max-w-5xl">
          <SplitVaultVisual ready={ready} />
        </div>
      </div>
    </section>
  );
}
