import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";

const NAV = [
  { href: "#product", label: "Product" },
  { href: "#security", label: "Security" },
  { href: "#pricing", label: "Pricing" },
];

export function MarketingLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-5 lg:px-8">
          <a href="#top" className="flex items-center gap-2.5">
            <img
              src="/brand/redcase-mark-white.svg"
              alt="RedCase mark"
              className="size-9"
            />
            <span className="font-display text-lg leading-none">
              <span className="font-semibold text-foreground">Red</span>
              <span className="font-light text-muted-foreground">Case</span>
            </span>
          </a>

          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => (
              <a
                key={item.href}
                href={item.href}
                className="rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors duration-200 hover:text-foreground"
              >
                {item.label}
              </a>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <Link
              to="/search"
              className="hidden rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors duration-200 hover:text-foreground sm:inline-flex"
            >
              Sign in
            </Link>
            <Link
              to="/signin"
              className="inline-flex items-center justify-center rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground shadow-sm transition-all duration-200 hover:bg-primary/90 hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
            >
              Start your firm
            </Link>
          </div>
        </div>
      </header>

      <main id="top">{children}</main>

      <footer className="border-t border-border/60">
        <div className="mx-auto max-w-7xl px-5 py-12 lg:px-8">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-center gap-2.5">
              <img
                src="/brand/redcase-mark-white.svg"
                alt="RedCase mark"
                className="size-8"
              />
              <span className="font-display text-base">
                <span className="font-semibold text-foreground">Red</span>
                <span className="font-light text-muted-foreground">Case</span>
                <span className="mt-1 block font-sans text-[11px] font-normal normal-case tracking-normal text-muted-foreground">
                  The Intelligent Engine for Modern Law
                </span>
              </span>
            </div>
            <div className="text-sm text-muted-foreground">
              Compliance: NDPA · DPIA filed · NDPC registration pending
            </div>
          </div>
          <div className="mt-10 border-t border-border/60 pt-6 text-xs text-muted-foreground/70">
            © 2026 RedCase.
          </div>
        </div>
      </footer>
    </div>
  );
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <div className="font-mono text-[11px] uppercase tracking-[0.28em] text-gold">
      {children}
    </div>
  );
}
