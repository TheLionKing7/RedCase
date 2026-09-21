import { CalendarClock, Swords, User } from "lucide-react";
import { Eyebrow } from "./MarketingLayout";

export function SecureMessenger() {
  return (
    <section className="border-y border-border/60 bg-surface/40">
      <div className="mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="grid grid-cols-1 items-center gap-12 lg:grid-cols-2">
          <div className="order-2 lg:order-1">
            {/* Chat-thread mock */}
            <div className="rounded-2xl border border-border bg-background/60 p-6 shadow-elevated">
              <div className="space-y-3">
                <div className="rounded-lg border border-primary/30 bg-primary/5 p-4">
                  <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-primary">
                    <CalendarClock className="size-3.5" />
                    Deadline tracker · agent
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-foreground/90">
                    FILING DUE: Motion on Notice &mdash; FBN v. Aetoes. 4 days
                    remain.
                  </p>
                </div>

                <div className="rounded-lg border border-gold/25 bg-gold/5 p-4">
                  <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-gold">
                    <Swords className="size-3.5" />
                    Red-Teamer · agent
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-foreground/90">
                    Battle card posted: opposing claim 3 rated 7/10 &mdash;
                    (2008) 5 NWLR (Pt. 1080) 227.
                  </p>
                </div>

                <div className="ml-auto max-w-[85%] rounded-lg border border-border bg-surface-raised p-4">
                  <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                    <User className="size-3.5" />
                    Partner · O. Adeyemi
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-foreground/90">
                    Confirmed — route the reply to chambers for sign-off.
                  </p>
                </div>
              </div>
            </div>
          </div>

          <div className="order-1 lg:order-2">
            <Eyebrow>Secure firm messenger</Eyebrow>
            <h2 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
              Your chambers, in your pocket.
            </h2>
            <p className="mt-5 text-base leading-relaxed text-muted-foreground">
              Matter channels where partners and associates actually work &mdash; with
              court deadlines, battle cards and analysis results posted into the thread by
              name. Encrypted under your firm&rsquo;s keys. Your client conversations
              never pass through Meta.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
