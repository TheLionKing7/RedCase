import { Bot, ScanText } from "lucide-react";
import { Eyebrow } from "./MarketingLayout";

const PIPELINE_PACKS = [
  "BriefBot",
  "Summons Response",
  "Contract Review",
  "Red-Teamer",
];

export function Workbench() {
  return (
    <section id="workbench" className="border-y border-border/60 bg-surface/40">
      <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="max-w-2xl">
          <Eyebrow>Workbench</Eyebrow>
          <h2 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
            A senior strategist on every matter.
          </h2>
        </div>

        <div className="mt-10 grid grid-cols-1 gap-5 lg:grid-cols-2">
          <div className="rounded-xl border border-border bg-background/40 p-7">
            <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.24em] text-gold">
              <ScanText className="size-4" />
              Analysis pipeline
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {PIPELINE_PACKS.map((pack) => (
                <span
                  key={pack}
                  className="rounded-full border border-gold/30 bg-gold/5 px-3 py-1 font-mono text-[11px] text-gold"
                >
                  {pack}
                </span>
              ))}
            </div>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              Upload an opposing brief; get procedural flaws, strength-rated
              counter-arguments, and binding authority &mdash; every section
              human-reviewable.
            </p>
          </div>

          <div className="rounded-xl border border-border bg-background/40 p-7">
            <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.24em] text-gold">
              <Bot className="size-4" />
              Legal Assistant
            </div>
            <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
              One assistant per lawyer. Learns how you work. Converses only in your
              workbench, under your permissions.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
