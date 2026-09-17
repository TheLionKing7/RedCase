import { Link } from "@tanstack/react-router";
import { Scale, Search, ShieldAlert, CalendarClock, Circle } from "lucide-react";
import type { ReactNode } from "react";

const NAV = [
  { to: "/", label: "Vault Search", sub: "Dual-Vault Engine", icon: Search },
  { to: "/red-teamer", label: "Case Red-Teamer", sub: "Adversarial analysis", icon: ShieldAlert },
  { to: "/tracker", label: "Statutory Tracker", sub: "Deadline computation", icon: CalendarClock },
] as const;

export function AppShell({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-72 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <div className="flex items-center gap-3 px-6 py-7">
          <div className="flex size-10 items-center justify-center rounded-lg bg-gold/12 glow-gold">
            <Scale className="size-5 text-gold" />
          </div>
          <div>
            <div className="font-display text-lg leading-none text-gradient-gold">Aetoes</div>
            <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
              Ops Hub
            </div>
          </div>
        </div>

        <nav className="flex flex-col gap-1 px-3">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              activeOptions={{ exact: item.to === "/" }}
              className="group rounded-lg px-3 py-3 text-sidebar-foreground transition-colors hover:bg-sidebar-accent"
              activeProps={{
                className:
                  "bg-sidebar-accent border-l-2 border-l-gold text-sidebar-accent-foreground",
              }}
            >
              <span className="flex items-center gap-3">
                <item.icon className="size-4 text-cyan" />
                <span className="flex flex-col">
                  <span className="text-sm font-medium">{item.label}</span>
                  <span className="text-[11px] text-muted-foreground">{item.sub}</span>
                </span>
              </span>
            </Link>
          ))}
        </nav>

        <div className="mt-auto space-y-3 px-6 py-6 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-2">
            <Circle className="size-2 fill-success text-success" />
            Vault A synced · 1,284 briefs
          </div>
          <div className="flex items-center gap-2">
            <Circle className="size-2 fill-success text-success" />
            Juris OS · 41,902 judgments
          </div>
          <div className="border-t border-sidebar-border pt-3 font-mono uppercase tracking-widest">
            Partner build v0.9
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-border bg-background/80 px-6 py-5 backdrop-blur-xl lg:px-10">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-cyan">
                {eyebrow}
              </div>
              <h1 className="mt-1 text-2xl font-semibold lg:text-3xl">{title}</h1>
            </div>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="rounded-full border border-gold/40 px-3 py-1 font-mono text-gold">
                CONFIDENTIAL · PRIVILEGED
              </span>
              <span className="hidden sm:inline">Tosin Adebayo · Managing Partner</span>
            </div>
          </div>
          <nav className="mt-4 flex gap-2 lg:hidden">
            {NAV.map((item) => (
              <Link
                key={item.to}
                to={item.to}
                activeOptions={{ exact: item.to === "/" }}
                className="rounded-md border border-border px-3 py-1.5 text-xs"
                activeProps={{ className: "border-gold text-gold" }}
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </header>
        <main className="flex-1 px-6 py-8 lg:px-10">{children}</main>
      </div>
    </div>
  );
}
