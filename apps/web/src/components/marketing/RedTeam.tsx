import { Swords, BadgeCheck, GitPullRequest } from "lucide-react";
import { Eyebrow } from "./MarketingLayout";

export function RedTeam() {
  return (
    <section className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
      <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-2">
        <div>
          <Eyebrow>Adversarial intelligence</Eyebrow>
          <h2 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
            Cross-examine every brief before the court does.
          </h2>
          <p className="mt-5 text-base leading-relaxed text-muted-foreground">
            Upload the other side&rsquo;s filing. RedCase tears it apart &mdash;
            procedural and jurisdictional flaws, your opponent&rsquo;s probable arguments
            strength-rated out of ten, and counter-arguments backed by binding Supreme
            Court and Court of Appeal authority. Every section human-reviewable before it
            reaches a partner.
          </p>
        </div>

        {/* Battle-card fragment */}
        <div className="relative">
          <div className="pointer-events-none absolute -inset-4 rounded-3xl bg-primary/10 blur-2xl" />
          <div className="relative rounded-2xl border border-border bg-surface p-6 shadow-elevated">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.24em] text-gold">
                <Swords className="size-4" />
                Battle card
              </div>
              <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/40 bg-amber-400/10 px-2.5 py-1 font-mono text-[9px] uppercase tracking-[0.18em] text-amber-300">
                <GitPullRequest className="size-3" />
                Manual review
              </span>
            </div>

            <div className="mt-5 rounded-lg border border-border/70 bg-background/40 p-4">
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                Opposing argument · strength
              </div>
              <div className="mt-2 mb-3 h-1.5 w-full overflow-hidden rounded-full bg-border/60">
                <div className="h-full w-[72%] rounded-full bg-gradient-to-r from-gold to-primary" />
              </div>
              <div className="flex items-baseline justify-between font-mono text-xs text-muted-foreground">
                <span>Plausible, factually thin</span>
                <span className="text-foreground">7 / 10</span>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-md border border-gold/30 bg-gold/5 px-2.5 py-1 font-mono text-[10px] text-gold">
                <BadgeCheck className="size-3" />
                (2008) 5 NWLR (Pt. 1080) 227
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
