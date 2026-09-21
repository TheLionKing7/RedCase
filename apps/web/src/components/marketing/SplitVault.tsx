const VAULT_A_ITEMS = ["Matter threads", "Briefs", "Pleadings", "Opinions"];
const VAULT_B_ITEMS = ["SC · Supreme Court", "CA · Court of Appeal", "NICN"];

export function SplitVaultVisual({ ready }: { ready: boolean }) {
  return (
    <div className="relative grid grid-cols-1 items-stretch gap-4 sm:grid-cols-[1fr_auto_1fr] sm:gap-6">
      <div className="pointer-events-none absolute left-1/2 top-1/2 hidden h-2 w-[34%] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-r from-primary/0 via-gold to-primary/0 blur-[2px] sm:block" />

      <div className="rounded-2xl border border-border bg-surface/70 p-6 shadow-elevated backdrop-blur-sm">
        {!ready ? (
          <SkeletonBox lines={4} />
        ) : (
          <>
            <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-gold">
              Vault A · Firm Brain
            </div>
            <ul className="mt-4 space-y-2">
              {VAULT_A_ITEMS.map((item) => (
                <li
                  key={item}
                  className="flex items-center gap-2.5 rounded-lg border border-border/70 bg-background/40 px-3 py-2 text-sm text-foreground/90"
                >
                  <span className="size-1.5 rounded-full bg-gold/70" />
                  {item}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="hidden flex-col items-center justify-center sm:flex">
        <div className="flex size-12 items-center justify-center rounded-full border border-gold/40 bg-surface-raised text-gold shadow-[0_0_40px_-8px_rgba(226,192,68,0.5)]">
          <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M12 2 4 5v6c0 5 3.4 9.4 8 11 4.6-1.6 8-6 8-11V5l-8-3Z" />
          </svg>
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-surface/70 p-6 shadow-elevated backdrop-blur-sm">
        {!ready ? (
          <SkeletonBox lines={4} />
        ) : (
          <>
            <div className="font-mono text-[10px] uppercase tracking-[0.24em] text-gold">
              Vault B · Juris OS
            </div>
            <div className="mt-3 font-mono text-3xl font-medium text-foreground">
              41,902
            </div>
            <div className="text-xs text-muted-foreground">indexed judgments</div>
            <ul className="mt-3 space-y-1.5">
              {VAULT_B_ITEMS.map((item) => (
                <li
                  key={item}
                  className="font-mono text-[11px] text-muted-foreground"
                >
                  {item}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

function SkeletonBox({ lines }: { lines: number }) {
  return (
    <div className="space-y-3" aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-9 animate-pulse rounded-lg bg-muted/50"
          style={{ opacity: 1 - i * 0.18 }}
        />
      ))}
    </div>
  );
}
