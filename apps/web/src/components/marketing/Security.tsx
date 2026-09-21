import { Lock, KeyRound, EyeOff, ScrollText, FileCheck2 } from "lucide-react";
import { Eyebrow } from "./MarketingLayout";

const BULLETS = [
  { icon: Lock, text: "AES-256 envelope encryption" },
  { icon: KeyRound, text: "per-document keys your firm controls" },
  { icon: EyeOff, text: "every AI call zero-retention" },
  { icon: ScrollText, text: "append-only audit trail" },
  { icon: FileCheck2, text: "NDPA DPIA filed" },
];

export function Security() {
  return (
    <section id="security" className="relative overflow-hidden border-t border-border/60">
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#1a1f2a]/70 to-transparent" />
      <div className="relative mx-auto max-w-7xl px-5 py-20 lg:px-8 lg:py-28">
        <div className="max-w-2xl">
          <Eyebrow>Security</Eyebrow>
          <h2 className="mt-4 font-display text-3xl font-semibold leading-tight sm:text-4xl">
            Built for privilege.
          </h2>
          <div className="mt-6 flex flex-wrap gap-2">
            {BULLETS.map(({ icon: Icon, text }) => (
              <span
                key={text}
                className="inline-flex items-center gap-2 rounded-full border border-gold/25 bg-gold/5 px-4 py-1.5 text-sm text-foreground/85"
              >
                <Icon className="size-4 text-gold" />
                {text}
              </span>
            ))}
          </div>
          <p className="mt-8 max-w-xl border-l-2 border-gold/50 pl-4 text-base leading-relaxed text-foreground/90">
            Client conversations never touch Meta, never touch a model provider&rsquo;s
            logs.
          </p>
        </div>
      </div>
    </section>
  );
}
