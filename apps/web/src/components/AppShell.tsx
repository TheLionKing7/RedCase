import { Link, useRouterState } from "@tanstack/react-router";
import {
  Bell,
  BookOpen,
  Bot,
  CalendarClock,
  Circle,
  CircleHelp,
  Home,
  Landmark,
  MessageSquare,
  Search,
  Settings2,
  ShieldAlert,
  SlidersHorizontal,
  Sparkles,
  Users,
  Vault,
  X,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { AssistantDock } from "@/components/AssistantDock";
import { ChromeTour, replayChromeTour } from "@/components/ChromeTour";
import { CommandPalette } from "@/components/CommandPalette";
import { getFirmAdmin } from "@/lib/auth/supabase";
import { useIdentity } from "@/lib/identity";
import { useDirectUnreadCount } from "@/lib/api/collaboration";
import type { AssistantContext } from "@/lib/api/assistantContext";

type Route =
  | "/home"
  | "/workbench"
  | "/search"
  | "/tracker"
  | "/firm-command"
  | "/red-teamer"
  | "/chats"
  | "/settings"
  | "/channels"
  | "/access-requests";
type Item = {
  label: string;
  detail: string;
  icon: typeof Home;
  to?: Route;
  adminOnly?: boolean;
};
const RAIL: Item[] = [
  { label: "Home", detail: "Inbox and priorities", icon: Home, to: "/home" },
  {
    label: "Workbench",
    detail: "Analysis and drafting",
    icon: Sparkles,
    to: "/workbench",
  },
  { label: "Vault", detail: "Firm and Juris OS", icon: Vault, to: "/search" },
  {
    label: "Messenger",
    detail: "Direct messages and matter channels",
    icon: MessageSquare,
    to: "/chats",
  },
  {
    label: "Tracker",
    detail: "Deadlines and court diary",
    icon: CalendarClock,
    to: "/tracker",
  },
  {
    label: "Firm Ops",
    detail: "Run the firm",
    icon: Landmark,
    to: "/firm-command",
    adminOnly: true,
  },
  {
    label: "Settings",
    detail: "Personal preferences",
    icon: Settings2,
    to: "/settings",
  },
];
const PANELS: Record<string, Item[]> = {
  Home: [
    {
      label: "Inbox",
      detail: "Assignments and mentions",
      icon: Home,
      to: "/home",
    },
    {
      label: "My deadlines",
      detail: "Upcoming statutory dates",
      icon: CalendarClock,
      to: "/tracker",
    },
    {
      label: "My matters",
      detail: "Personal workbench view",
      icon: BookOpen,
      to: "/workbench",
    },
  ],
  Workbench: [
    {
      label: "SmartBrief",
      detail: "Structured legal analysis",
      icon: Sparkles,
      to: "/workbench",
    },
    {
      label: "Red-Teamer",
      detail: "Adversarial strategy review",
      icon: ShieldAlert,
      to: "/red-teamer",
    },
    {
      label: "My analyses",
      detail: "Recent work product",
      icon: BookOpen,
      to: "/workbench",
    },
  ],
  Vault: [
    { label: "Internal", detail: "Firm documents", icon: Vault, to: "/search" },
    {
      label: "Juris OS",
      detail: "Public jurisprudence",
      icon: Landmark,
      to: "/search",
    },
    {
      label: "Search",
      detail: "Cross-vault research",
      icon: Search,
      to: "/search",
    },
    {
      label: "Access requests",
      detail: "Named grants and approvals",
      icon: ShieldAlert,
      to: "/access-requests",
    },
  ],
  Messenger: [
    {
      label: "DM",
      detail: "Private firm conversations",
      icon: Users,
      to: "/chats",
    },
    {
      label: "Matter channels",
      detail: "Forum-style case rooms",
      icon: MessageSquare,
      to: "/channels",
    },
    {
      label: "Archived",
      detail: "Read-only concluded matters",
      icon: BookOpen,
      to: "/channels",
    },
  ],
  Tracker: [
    {
      label: "Deadlines",
      detail: "Computed obligations",
      icon: CalendarClock,
      to: "/tracker",
    },
    {
      label: "Court diary",
      detail: "Scheduled activities",
      icon: BookOpen,
      to: "/tracker",
    },
  ],
  "Firm Ops": [
    {
      label: "Overview",
      detail: "Firm command center",
      icon: Landmark,
      to: "/firm-command",
    },
    {
      label: "Team and grants",
      detail: "Seats, roles and access",
      icon: Users,
      to: "/firm-command",
    },
  ],
  Settings: [
    {
      label: "Assistant Persona",
      detail: "Personal writing preferences",
      icon: Bot,
      to: "/settings",
    },
  ],
};

function TaskBarItem({
  icon: Icon,
  label,
  to,
  unread = 0,
}: {
  icon: typeof Home;
  label: string;
  to: "/pins" | "/chats" | "/channels" | "/threads" | "/contacts";
  unread?: number;
}) {
  const active = useRouterState({
    select: (state) => state.location.pathname === to,
  });
  return (
    <Link
      to={to}
      aria-current={active ? "page" : undefined}
      className={`relative group inline-flex items-center gap-1.5 rounded-md border-l-2 px-2 py-1.5 transition-all duration-200 hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold ${active ? "border-primary text-gold" : "border-transparent text-muted-foreground"}`}
      title={label}
    >
      <Icon className="size-3.5" />
      <span>{label}</span>
      {unread > 0 && (
        <span
          className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-primary px-1 text-center font-mono text-[9px] leading-4 text-white"
          aria-label={`${unread} unread messages`}
        >
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </Link>
  );
}

function DirectUnreadBadge() {
  const unread = useDirectUnreadCount();
  return (
    <TaskBarItem
      icon={MessageSquare}
      label="DM"
      to="/chats"
      unread={Math.min(unread.data?.unread_count ?? 0, 99)}
    />
  );
}

function roleDepartment(role: string | null, admin: boolean): string {
  if (admin) return "Admin";
  const normalized = (role ?? "").toLowerCase();
  if (normalized.includes("partner")) return "Partner";
  if (normalized.includes("associate") || normalized.includes("senior"))
    return "Associate";
  if (normalized.includes("finance") || normalized.includes("account"))
    return "Finance";
  if (normalized.includes("hr") || normalized.includes("human")) return "HR";
  return normalized.includes("staff") ? "Staff" : "Staff";
}

export function AppShell({
  title,
  eyebrow,
  children,
  assistantContext,
}: {
  title: string;
  eyebrow: string;
  children: ReactNode;
  assistantContext?: AssistantContext;
}) {
  const firmAdmin = getFirmAdmin();
  const identity = useIdentity();
  const pathname = useRouterState({
    select: (state) => state.location.pathname,
  });
  const current = pathname.startsWith("/settings")
    ? "Settings"
    : pathname.startsWith("/firm-command")
      ? "Firm Ops"
      : pathname.startsWith("/search") ||
          pathname.startsWith("/access-requests")
        ? "Vault"
        : pathname.startsWith("/chats") ||
            pathname.startsWith("/channels") ||
            pathname.startsWith("/contacts") ||
            pathname.startsWith("/pins")
          ? "Messenger"
          : pathname.startsWith("/threads")
            ? "Messenger"
            : (RAIL.find(
                (item) =>
                  item.to &&
                  (pathname === item.to || pathname.startsWith(`${item.to}/`)),
              )?.label ?? "Home");
  const [activeRail, setActiveRail] = useState(current);
  const [panelOpen, setPanelOpen] = useState(true);
  const [compact, setCompact] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  useEffect(() => setActiveRail(current), [current]);
  useEffect(() => {
    const openAssistant = () => setAssistantOpen(true);
    window.addEventListener("redcase:assistant-open", openAssistant);
    return () =>
      window.removeEventListener("redcase:assistant-open", openAssistant);
  }, []);
  const visibleRail = RAIL.filter((item) => !item.adminOnly || firmAdmin);
  const activeItem =
    visibleRail.find((item) => item.label === activeRail) ?? visibleRail[0];
  const panelItems = PANELS[activeItem?.label ?? "Home"] ?? [];
  const selectedPanelItem =
    panelItems.find((item) => item.to === pathname) ??
    panelItems.find((item) => item.to && pathname.startsWith(`${item.to}/`));
  const department = roleDepartment(identity.role, firmAdmin);
  const roleSubtitle = department;
  const dockContext: AssistantContext = assistantContext ?? {
    bench: pathname.startsWith("/red-teamer")
      ? "Red-Teamer"
      : pathname.startsWith("/workbench")
        ? "SmartBrief"
        : pathname.startsWith("/search")
          ? "Researcher"
          : pathname.startsWith("/tracker")
            ? "Reviewer"
            : "Home",
  };

  return (
    <div className="min-h-screen bg-background">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[4.5rem] flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <div className="flex h-[4.5rem] items-center justify-center border-b border-sidebar-border">
          <img
            src="/brand/redcase-mark-white.svg"
            alt="RedCase"
            className="size-9"
          />
        </div>
        <nav
          aria-label="Primary navigation"
          className="flex flex-1 flex-col items-center gap-2 px-2 py-5"
        >
          {visibleRail.map((item) => {
            const selected = activeRail === item.label;
            const body = (
              <span
                className={`relative flex w-full flex-col items-center gap-1 border-l-2 px-1 py-3 text-center transition-all duration-200 ${selected ? "border-primary text-gold" : "border-transparent text-steel hover:text-foreground"}`}
              >
                <item.icon className="size-5" />
                <span className="font-mono text-[9px] uppercase tracking-wide">
                  {item.label === "Workbench"
                    ? "Work"
                    : item.label === "Messenger"
                      ? "Chat"
                      : item.label}
                </span>
              </span>
            );
            return item.to ? (
              <Link
                key={item.label}
                to={item.to}
                onClick={() => setActiveRail(item.label)}
                aria-label={item.label}
                aria-current={selected ? "page" : undefined}
              >
                {body}
              </Link>
            ) : (
              <button
                key={item.label}
                type="button"
                onClick={() => {
                  setActiveRail(item.label);
                  setPanelOpen(true);
                }}
                aria-label={item.label}
                aria-expanded={selected}
              >
                {body}
              </button>
            );
          })}
        </nav>
        <button
          type="button"
          onClick={() => setPanelOpen((open) => !open)}
          className="m-2 flex items-center justify-center rounded-xl p-3 text-steel transition-all duration-200 hover:bg-sidebar-accent hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"
          aria-label={
            panelOpen ? "Collapse navigation panel" : "Expand navigation panel"
          }
        >
          {panelOpen ? (
            <X className="size-4" />
          ) : (
            <SlidersHorizontal className="size-4" />
          )}
        </button>
      </aside>

      {panelOpen && (
        <aside className="fixed inset-y-0 left-[4.5rem] z-20 hidden w-64 flex-col border-r border-sidebar-border bg-[#171a21] lg:flex">
          <div className="border-b border-sidebar-border px-5 py-6">
            <div className="font-display text-lg leading-none">
              <span className="font-semibold text-foreground">Red</span>
              <span className="font-light text-muted-foreground">Case</span>
            </div>
            <div className="mt-2 font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
              Aetoes Legal · {department}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-5">
            <div className="px-3 font-mono text-[9px] uppercase tracking-[0.22em] text-steel">
              {activeItem?.label}
            </div>
            <p className="px-3 pt-2 text-xs text-muted-foreground">
              {activeItem?.detail}
            </p>
            <nav
              className="mt-5 space-y-1"
              aria-label={`${activeItem?.label} navigation`}
            >
              {panelItems.map((item) => {
                const selected = item === selectedPanelItem;
                const cls = `group flex items-start gap-3 border-l-2 px-3 py-3 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold ${selected ? "border-primary text-[#f3e8c8]" : "border-transparent text-sidebar-foreground hover:text-foreground"}`;
                return item.to ? (
                  <Link
                    key={item.label}
                    to={item.to}
                    className={cls}
                    aria-current={selected ? "page" : undefined}
                  >
                    <item.icon
                      className={`mt-0.5 size-4 shrink-0 ${selected ? "text-primary" : "text-steel group-hover:text-primary"}`}
                    />
                    <span>
                      <span className="block text-sm">{item.label}</span>
                      <span className="block text-[11px] text-muted-foreground">
                        {item.detail}
                      </span>
                    </span>
                  </Link>
                ) : (
                  <div key={item.label} className={`${cls} opacity-60`}>
                    <item.icon className="mt-0.5 size-4 shrink-0 text-steel" />
                    <span>
                      <span className="block text-sm">{item.label}</span>
                      <span className="block text-[11px] text-muted-foreground">
                        {item.detail}
                      </span>
                    </span>
                  </div>
                );
              })}
            </nav>
          </div>
          <div className="border-t border-sidebar-border px-5 py-4 text-xs text-muted-foreground">
            <p>● &nbsp;Vault A synced</p>
            <p className="mt-2">● &nbsp;Juris OS synced</p>
            <p className="mt-3 font-mono text-[9px] uppercase tracking-widest">
              {roleSubtitle}
            </p>
          </div>
        </aside>
      )}

      <div
        className={`${panelOpen ? "lg:ml-[20.5rem]" : "lg:ml-[4.5rem]"} flex min-h-screen flex-col transition-[margin] duration-200`}
      >
        <header className="sticky top-0 z-10 border-b border-border bg-background/95 px-5 py-4 backdrop-blur-xl lg:px-8">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-steel">
                {eyebrow}
              </div>
              <h1 className="mt-1 truncate text-2xl font-semibold lg:text-3xl">
                {title}
              </h1>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <button
                type="button"
                className="hidden items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2 text-left transition-all duration-200 hover:border-gold/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold sm:flex"
                onClick={() => setPaletteOpen(true)}
                aria-label="Open command palette"
              >
                <Search className="size-4 text-steel" />
                <span className="hidden lg:inline">Search anything</span>
                <kbd className="rounded border border-border px-1.5 py-0.5 font-mono text-[9px]">
                  ⌘K
                </kbd>
              </button>
              <button
                type="button"
                className="rounded-lg p-2 transition-all duration-200 hover:bg-surface hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"
                aria-label="Notifications"
              >
                <Bell className="size-4" />
              </button>
              <button
                type="button"
                onClick={replayChromeTour}
                className="rounded-lg p-2 transition-all duration-200 hover:bg-surface hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"
                aria-label="Help and replay guided tour"
              >
                <CircleHelp className="size-4" />
              </button>
              <span className="hidden rounded-full border border-gold/40 px-3 py-1 font-mono text-[10px] text-gold xl:inline">
                CONFIDENTIAL · PRIVILEGED
              </span>
            </div>
          </div>
          <nav
            aria-label="Primary navigation"
            className="mt-4 flex gap-2 overflow-x-auto lg:hidden"
          >
            {visibleRail
              .filter((item) => item.to)
              .map((item) => (
                <Link
                  key={item.label}
                  to={item.to!}
                  className={`whitespace-nowrap border-l-2 px-3 py-1.5 text-xs transition-all duration-200 ${current === item.label ? "border-primary text-gold" : "border-transparent text-muted-foreground"}`}
                >
                  {item.label}
                </Link>
              ))}
          </nav>
        </header>
        <main
          className={`flex-1 px-5 py-8 pb-24 transition-all duration-200 lg:px-8 ${compact ? "lg:py-5" : ""}`}
        >
          {children}
        </main>
        <footer
          className={`fixed bottom-0 right-0 z-20 flex h-[3.75rem] items-center justify-between gap-4 overflow-x-auto border-t border-border bg-sidebar/95 px-5 py-2.5 backdrop-blur-xl transition-all duration-200 lg:px-8 ${panelOpen ? "lg:left-[20.5rem]" : "lg:left-[4.5rem]"}`}
        >
          <nav
            aria-label="Communication task bar"
            className="flex min-w-max items-center gap-1 text-[11px]"
          >
            <TaskBarItem icon={BookOpen} label="Pins" to="/pins" />
            <DirectUnreadBadge />
            <TaskBarItem icon={Landmark} label="Channels" to="/channels" />
            <TaskBarItem icon={CircleHelp} label="Threads" to="/threads" />
            <TaskBarItem icon={Users} label="Contacts" to="/contacts" />
          </nav>
          <div className="flex min-w-max items-center gap-2">
            <span className="hidden items-center gap-1.5 text-[10px] text-muted-foreground sm:flex">
              <Circle className="size-2 fill-success text-success" /> Team
              online
            </span>
            <button
              type="button"
              onClick={() => setAssistantOpen(true)}
              className="flex items-center gap-1.5 rounded-md bg-gold/10 px-2 py-1 text-[11px] font-medium text-gold transition-all duration-200 hover:bg-gold/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"
              aria-label="Open Assistant dock"
            >
              <Bot className="size-3.5" /> Assistant
            </button>
            <button
              type="button"
              onClick={() => setCompact((value) => !value)}
              className="flex shrink-0 items-center gap-2 rounded-md px-2 py-1 text-[11px] text-muted-foreground transition-all duration-200 hover:bg-sidebar-accent hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"
              aria-label="Toggle density"
            >
              <Settings2 className="size-3.5" />{" "}
              {compact ? "Compact" : "Comfortable"}
            </button>
          </div>
        </footer>
      </div>
      <ChromeTour isFirmAdmin={firmAdmin} />
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onAssistant={() => setAssistantOpen(true)}
        onToggleDensity={() => setCompact((value) => !value)}
      />
      <AssistantDock
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        context={dockContext}
        persistent
      />
    </div>
  );
}
