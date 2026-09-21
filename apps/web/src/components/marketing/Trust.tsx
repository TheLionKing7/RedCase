import { ShieldX } from "lucide-react";
import { Eyebrow } from "./MarketingLayout";

export function Trust() {
  return (
    <section className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
      <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-[1fr_1fr]">
        <div>
          <Eyebrow>The trust section</Eyebrow>
          <h2 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
            The engine that refuses to guess.
          </h2>
          <p className="mt-5 text-base leading-relaxed text-muted-foreground">
            When the authority isn&rsquo;t in the vaults, RedCase says so &mdash;
            in writing. Every proposition carries a page-pinned citation you can open and
            verify. Fabricated citations are a hard failure, tested every release, not a
            disclaimer in the footer.
          </p>
        </div>

        {/* The refusal panel — designed artifact */}
        <div className="relative">
          <div className="pointer-events-none absolute -inset-4 rounded-3xl bg-primary/10 blur-2xl" />
          <div className="relative border-l-4 border-l-primary rounded-r-2xl rounded-l-none bg-surface p-8 shadow-elevated">
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.28em] text-primary">
              <ShieldX className="size-4" />
              Refused · citation integrity
            </div>
            <p className="mt-4 font-display text-2xl leading-snug">
              &ldquo;No binding precedent found in Vault B.&rdquo;
            </p>
            <p className="mt-4 border-t border-border/70 pt-4 text-sm leading-relaxed text-muted-foreground">
              The retrieved passages did not meet the verification gate. Under the
              citation-integrity contract, RedCase shows no answer rather than an
              unverified one &mdash; a fabricated citation is never displayed.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
