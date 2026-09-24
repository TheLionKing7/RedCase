import { Link, useRouterState } from "@tanstack/react-router";
import { Bell, BookOpen, CalendarClock, Circle, CircleHelp, Home, Landmark, MessageSquare, Search, Settings2, ShieldAlert, SlidersHorizontal, Sparkles, Users, Vault, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { getFirmAdmin } from "@/lib/auth/supabase";
import { useIdentity } from "@/lib/identity";

type ShellRoute = "/home" | "/workbench" | "/search" | "/tracker" | "/firm-command" | "/red-teamer";
type Item = { label: string; detail: string; icon: typeof Home; to?: ShellRoute; adminOnly?: boolean };
const RAIL: Item[] = [
  { label: "Home", detail: "Inbox and priorities", icon: Home, to: "/home" },
  { label: "Workbench", detail: "Analysis and drafting", icon: Sparkles, to: "/workbench" },
  { label: "Vault", detail: "Firm and Juris OS", icon: Vault, to: "/search" },
  { label: "Messenger", detail: "Matter channels and direct", icon: MessageSquare },
  { label: "Tracker", detail: "Deadlines and court diary", icon: CalendarClock, to: "/tracker" },
  { label: "Firm Ops", detail: "Run the firm", icon: Landmark, to: "/firm-command", adminOnly: true },
];
const PANELS: Record<string, Item[]> = {
  Home: [{ label: "Inbox", detail: "Assignments and mentions", icon: Home, to: "/home" }, { label: "My deadlines", detail: "Upcoming statutory dates", icon: CalendarClock, to: "/tracker" }, { label: "My matters", detail: "Personal workbench view", icon: BookOpen, to: "/workbench" }],
  Workbench: [{ label: "SmartBrief", detail: "Structured legal analysis", icon: Sparkles, to: "/workbench" }, { label: "Red-Teamer", detail: "Adversarial strategy review", icon: ShieldAlert, to: "/red-teamer" }, { label: "My analyses", detail: "Recent work product", icon: BookOpen, to: "/workbench" }],
  Vault: [{ label: "Internal", detail: "Aetoes firm documents", icon: Vault, to: "/search" }, { label: "Juris OS", detail: "Public jurisprudence", icon: Landmark, to: "/search" }, { label: "Search", detail: "Cross-vault research", icon: Search, to: "/search" }],
  Messenger: [{ label: "Matter channels", detail: "Forum-style case rooms", icon: MessageSquare }, { label: "Direct", detail: "Private firm conversations", icon: Users }, { label: "Archived", detail: "Read-only concluded matters", icon: BookOpen }],
  Tracker: [{ label: "Deadlines", detail: "Computed obligations", icon: CalendarClock, to: "/tracker" }, { label: "Court diary", detail: "Scheduled activities", icon: BookOpen, to: "/tracker" }],
  "Firm Ops": [{ label: "Overview", detail: "Firm command center", icon: Landmark, to: "/firm-command" }, { label: "Team and grants", detail: "Seats, roles and access", icon: Users, to: "/firm-command" }],
};

export function AppShell({ title, eyebrow, children }: { title: string; eyebrow: string; children: ReactNode }) {
  const firmAdmin = getFirmAdmin();
  const identity = useIdentity();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const current = RAIL.find((item) => item.to && pathname.startsWith(item.to))?.label ?? "Home";
  const [activeRail, setActiveRail] = useState(current);
  const [panelOpen, setPanelOpen] = useState(true);
  const [compact, setCompact] = useState(false);
  const visibleRail = RAIL.filter((item) => !item.adminOnly || firmAdmin);
  const activeItem = visibleRail.find((item) => item.label === activeRail) ?? visibleRail[0];
  const panelItems = PANELS[activeItem?.label ?? "Home"] ?? [];

  return <div className="flex min-h-screen bg-background">
    <aside className="hidden w-[4.5rem] shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
      <div className="flex h-[4.5rem] items-center justify-center border-b border-sidebar-border"><img src="/brand/redcase-mark-white.svg" alt="RedCase" className="size-9" /></div>
      <nav className="flex flex-1 flex-col items-center gap-2 px-2 py-5">{visibleRail.map((item) => { const content = <span className={`flex w-full flex-col items-center gap-1 rounded-xl px-1 py-3 text-center transition-all duration-200 ${activeRail === item.label ? "bg-sidebar-accent text-gold shadow-sm" : "text-steel hover:bg-sidebar-accent/70 hover:text-foreground"}`}><item.icon className="size-5" /><span className="font-mono text-[9px] uppercase tracking-wide">{item.label === "Workbench" ? "Work" : item.label === "Messenger" ? "Chat" : item.label}</span></span>; return item.to ? <Link key={item.label} to={item.to} onClick={() => setActiveRail(item.label)} aria-label={item.label}>{content}</Link> : <button key={item.label} type="button" onClick={() => { setActiveRail(item.label); setPanelOpen(true); }} aria-label={item.label}>{content}</button>; })}</nav>
      <button type="button" onClick={() => setPanelOpen((open) => !open)} className="m-2 flex items-center justify-center rounded-xl p-3 text-steel transition-all duration-200 hover:bg-sidebar-accent hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold" aria-label={panelOpen ? "Collapse navigation panel" : "Expand navigation panel"}>{panelOpen ? <X className="size-4" /> : <SlidersHorizontal className="size-4" />}</button>
    </aside>
    {panelOpen && <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-border bg-[#171a21] lg:flex">
      <div className="border-b border-sidebar-border px-5 py-6"><div className="font-display text-lg leading-none"><span className="font-semibold text-foreground">Red</span><span className="font-light text-muted-foreground">Case</span></div><div className="mt-2 font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">Aetoes Legal · Tenant Zero</div></div>
      <div className="flex-1 px-3 py-5"><div className="px-3 font-mono text-[9px] uppercase tracking-[0.22em] text-steel">{activeItem?.label}</div><p className="px-3 pt-2 text-xs text-muted-foreground">{activeItem?.detail}</p><nav className="mt-5 space-y-1">{panelItems.map((item) => item.to ? <Link key={item.label} to={item.to} className="group flex items-start gap-3 rounded-lg px-3 py-3 text-sidebar-foreground transition-all duration-200 hover:bg-sidebar-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"><item.icon className="mt-0.5 size-4 shrink-0 text-steel group-hover:text-gold" /><span><span className="block text-sm">{item.label}</span><span className="block text-[11px] text-muted-foreground">{item.detail}</span></span></Link> : <div key={item.label} className="flex items-start gap-3 rounded-lg px-3 py-3 opacity-60"><item.icon className="mt-0.5 size-4 shrink-0 text-steel" /><span><span className="block text-sm">{item.label}</span><span className="block text-[11px] text-muted-foreground">{item.detail}</span></span></div>)}</nav></div>
      <div className="space-y-3 border-t border-sidebar-border px-5 py-5 text-[11px] text-muted-foreground"><div className="flex items-center gap-2"><Circle className="size-2 fill-success text-success" /> Vault A synced</div><div className="flex items-center gap-2"><Circle className="size-2 fill-success text-success" /> Juris OS synced</div><div className="font-mono text-[9px] uppercase tracking-widest">Partner build v0.9</div></div>
    </aside>}
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="sticky top-0 z-20 border-b border-border bg-background/90 px-5 py-4 backdrop-blur-xl lg:px-8"><div className="flex items-center justify-between gap-4"><div className="min-w-0"><div className="font-mono text-[10px] uppercase tracking-[0.28em] text-steel">{eyebrow}</div><h1 className="mt-1 truncate text-2xl font-semibold lg:text-3xl">{title}</h1></div><div className="flex items-center gap-2 text-xs text-muted-foreground"><button type="button" className="hidden items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-left transition-all duration-200 hover:border-gold/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold sm:flex" aria-label="Open command palette"><Search className="size-4 text-steel" /><span className="hidden lg:inline">Search anything</span><kbd className="rounded border border-border px-1.5 py-0.5 font-mono text-[9px]">⌘K</kbd></button><button type="button" className="rounded-lg p-2 transition-all duration-200 hover:bg-surface hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold" aria-label="Notifications"><Bell className="size-4" /></button><button type="button" className="rounded-lg p-2 transition-all duration-200 hover:bg-surface hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold" aria-label="Help"><CircleHelp className="size-4" /></button><span className="hidden rounded-full border border-gold/40 px-3 py-1 font-mono text-[10px] text-gold xl:inline">CONFIDENTIAL · PRIVILEGED</span><span className="flex items-center gap-2 rounded-full border border-border/70 bg-sidebar px-2.5 py-1"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-gold/20 text-[9px] font-bold text-gold">{identity.name.slice(0, 2).toUpperCase()}</span><span className="hidden font-medium text-foreground sm:inline">{identity.name}</span></span></div></div><nav className="mt-4 flex gap-2 overflow-x-auto lg:hidden">{visibleRail.filter((item) => item.to).map((item) => <Link key={item.label} to={item.to!} className="whitespace-nowrap rounded-md border border-border px-3 py-1.5 text-xs transition-all duration-200 hover:border-gold/50">{item.label}</Link>)}</nav></header>
      <main className={`shell-main flex-1 px-5 py-8 transition-all duration-200 lg:px-8 ${compact ? "lg:py-5" : ""}`}>{children}</main>
      <footer className="sticky bottom-0 z-10 flex items-center justify-between border-t border-border bg-sidebar/95 px-5 py-2.5 backdrop-blur-xl lg:px-8"><div className="flex items-center gap-4 text-[11px] text-muted-foreground"><span className="flex items-center gap-1.5"><BookOpen className="size-3.5" /> Pins</span><span className="flex items-center gap-1.5"><MessageSquare className="size-3.5" /> Chats</span><span className="hidden items-center gap-1.5 sm:flex"><Users className="size-3.5" /> Contacts</span></div><button type="button" onClick={() => setCompact((value) => !value)} className="flex items-center gap-2 rounded-md px-2 py-1 text-[11px] text-muted-foreground transition-all duration-200 hover:bg-sidebar-accent hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold" aria-label="Toggle density"><Settings2 className="size-3.5" /> {compact ? "Compact" : "Comfortable"}</button></footer>
    </div>
  </div>;
}
