import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  Briefcase,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
  Clock3,
  FileClock,
  Gavel,
  Loader2,
  Scale,
  Timer,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { useIdentity } from "@/lib/identity";
import { useAnalyses } from "@/lib/api/workbench";
import { useDeadlineEvents, type DeadlineEvent } from "@/lib/api/deadlines";
import { apiGet } from "@/lib/api/client";
import { useQuery } from "@tanstack/react-query";
import {
  useActivitySessions,
  useClockIn,
  useClockOut,
} from "@/lib/api/activity";
import type { ActivitySessionGroup } from "@/lib/api/activity";
import { useCourtDiaryEntries } from "@/lib/api/court-diary";

type HomeView = "Inbox" | "Today" | "My deadlines" | "My matters";
type HomeMatter = {
  id: string;
  matter_ref: string;
  status: string;
  progress_note: string | null;
};
const AREAS = ["Research", "Workbench", "General"] as const;

export const Route = createFileRoute("/_authed/home")({
  head: () => ({
    meta: [
      { title: "Home — RedCase" },
      { name: "description", content: "Your RedCase workspace." },
    ],
  }),
  component: Home,
});

function Home() {
  const identity = useIdentity();
  const analyses = useAnalyses();
  const deadlines = useDeadlineEvents();
  const diary = useCourtDiaryEntries();
  const matters = useQuery({
    queryKey: ["matters", "my"],
    queryFn: () => apiGet<{ matters: HomeMatter[] }>("/v1/matters/my"),
  });
  const [view, setView] = useState<HomeView>("Inbox");
  const [selectedMatterId, setSelectedMatterId] = useState<string | null>(null);
  useEffect(() => {
    const selectView = (event: Event) => {
      const selected = (event as CustomEvent<HomeView>).detail;
      if (["Inbox", "Today", "My deadlines", "My matters"].includes(selected)) {
        setView(selected);
        setSelectedMatterId(null);
      }
    };
    window.addEventListener("redcase:home-view", selectView);
    return () => window.removeEventListener("redcase:home-view", selectView);
  }, []);
  const today = new Date().toISOString().slice(0, 10);
  const openDeadlines = useMemo(
    () =>
      (deadlines.data ?? [])
        .filter((event) => event.status !== "DISMISSED")
        .sort((a, b) => a.due_date.localeCompare(b.due_date)),
    [deadlines.data],
  );
  const todaysItems = useMemo(() => {
    const due = (deadlines.data ?? [])
      .filter((event) => event.due_date === today)
      .map((event) => ({
        id: event.id,
        title: event.description,
        kind: event.event_type,
        when: event.due_date,
      }));
    const listed = (diary.data ?? [])
      .filter(
        (entry) =>
          entry.starts_at.slice(0, 10) === today &&
          entry.status === "SCHEDULED",
      )
      .map((entry) => ({
        id: entry.id,
        title: entry.title,
        kind: entry.entry_type,
        when: entry.starts_at,
      }));
    return [...due, ...listed].sort((a, b) => a.when.localeCompare(b.when));
  }, [deadlines.data, diary.data, today]);
  const pending =
    analyses.isPending ||
    deadlines.isPending ||
    diary.isPending ||
    matters.isPending;
  const failed =
    analyses.isError || deadlines.isError || diary.isError || matters.isError;
  return (
    <AppShell
      eyebrow={identity.eyebrow}
      title="Welcome"
      sidebarContent={
        <TimeLogger
          compact
          matters={(matters.data?.matters ?? []).filter(
            (matter) =>
              !["CLOSED", "COMPLETED", "ARCHIVED"].includes(
                matter.status.toUpperCase(),
              ),
          )}
        />
      }
    >
      <div className="mx-auto max-w-6xl space-y-6 pb-16">
        <section
          className="panel glow-gold p-5 sm:p-6"
          aria-label="Workbench and time logger"
        >
          <div className="flex flex-col items-stretch gap-6 xl:flex-row xl:items-center">
            <div className="min-w-0 flex-1">
              <div className="font-mono text-[10px] uppercase tracking-[0.28em] text-gold">
                {identity.eyebrow}
              </div>
              <h2 className="mt-1 font-display text-2xl font-semibold">
                Workbench — your matters, your authority
              </h2>
              <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
                Run adversarial briefs, summons responses and contract reviews,
                then verify against Nigerian law with page-pinned citations.
                Pick up where you left off.
              </p>
              <Link
                to="/workbench"
                className="mt-4 inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2.5 text-sm font-semibold text-background transition-all duration-200 hover:bg-gold/90 hover:shadow-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/50"
              >
                Open Workbench <ArrowUpRight className="size-4" />
              </Link>
            </div>
            <div className="lg:hidden">
              <TimeLogger
                matters={(matters.data?.matters ?? []).filter(
                  (matter) =>
                    !["CLOSED", "COMPLETED", "ARCHIVED"].includes(
                      matter.status.toUpperCase(),
                    ),
                )}
              />
            </div>
          </div>
        </section>

        <section aria-labelledby="workspace-heading" className="space-y-4">
          <div>
            <h2
              id="workspace-heading"
              className="mt-1 font-display text-xl font-semibold"
            >
              Workspace
            </h2>
          </div>
          <div className="space-y-4">
            <nav
              aria-label="Workspace sections"
              className="flex gap-2 overflow-x-auto rounded-xl border border-border bg-sidebar/60 p-2 lg:hidden"
            >
              {(
                [
                  ["Inbox", Briefcase, "Assignments and recent work"],
                  ["Today", CalendarClock, "Hearings, filings and reviews"],
                  ["My deadlines", Clock3, "Upcoming dates and reminders"],
                  ["My matters", Scale, "In-progress matters assigned to you"],
                ] as const
              ).map(([label, Icon, description]) => (
                <button
                  key={label}
                  type="button"
                  onClick={() => {
                    setView(label);
                    window.dispatchEvent(
                      new CustomEvent("redcase:home-view", { detail: label }),
                    );
                  }}
                  aria-current={view === label ? "page" : undefined}
                  className={`flex min-w-max items-center gap-3 rounded-r-lg border-l-2 px-3 py-3 text-left transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${view === label ? "border-primary bg-[#f3e8c8]/[0.08] text-[#f3e8c8]" : "border-transparent text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-foreground"}`}
                >
                  <Icon
                    className={`size-4 shrink-0 ${view === label ? "text-primary" : "text-steel"}`}
                  />
                  <span>
                    <span className="block text-sm font-medium">{label}</span>
                    <span className="hidden text-[11px] text-muted-foreground lg:block">
                      {description}
                    </span>
                  </span>
                </button>
              ))}
            </nav>
            <div
              className="min-h-[360px] rounded-xl border border-border bg-background/70 p-4 sm:p-6"
              aria-live="polite"
            >
              <div className="mb-5 flex items-center justify-between gap-3">
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-steel">
                    Workspace
                  </p>
                  <h3 className="mt-1 font-display text-lg font-semibold">
                    {view}
                  </h3>
                </div>
                {view === "My deadlines" && (
                  <Link
                    to="/tracker"
                    className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-xs font-medium transition-all duration-200 hover:border-primary/60 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    Open in Tracker <ArrowUpRight className="size-3.5" />
                  </Link>
                )}
              </div>
              {pending ? (
                <LoadingRows />
              ) : failed ? (
                <ErrorState />
              ) : view === "Inbox" ? (
                <InboxView
                  analyses={analyses.data ?? []}
                  deadlines={openDeadlines.slice(0, 5)}
                  matters={matters.data?.matters ?? []}
                />
              ) : view === "Today" ? (
                <TodayView items={todaysItems} />
              ) : view === "My deadlines" ? (
                <DeadlinesView events={openDeadlines} />
              ) : (
                <MattersView
                  matters={matters.data?.matters ?? []}
                  selectedMatterId={selectedMatterId}
                  onSelectMatter={setSelectedMatterId}
                  onBack={() => setSelectedMatterId(null)}
                />
              )}
            </div>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

function TimeLogger({
  matters,
  compact = false,
}: {
  matters: HomeMatter[];
  compact?: boolean;
}) {
  const sessions = useActivitySessions();
  const clockIn = useClockIn();
  const clockOut = useClockOut();
  const [selection, setSelection] = useState("area:General");
  const active = sessions.data?.sessions.find((session) => !session.ended_at);
  const busy = clockIn.isPending || clockOut.isPending;
  const start = () => {
    const [target_type, target_ref] = selection.split(":");
    const selectedMatter = matters.find((matter) => matter.id === target_ref);
    const area =
      target_type === "matter"
        ? (selectedMatter?.matter_ref ?? "General")
        : target_ref;
    if (target_type && target_ref)
      clockIn.mutate({
        area,
        target_type: target_type as "matter" | "area",
        target_ref,
      });
  };
  const groups = sessions.data?.groups ?? [];
  const fmt = (seconds: number) =>
    `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return (
    <div
      className={`w-full rounded-xl border border-border/70 bg-background/70 ${compact ? "p-3" : "p-4 xl:w-[300px] xl:shrink-0"}`}
    >
      <div className="flex items-center gap-2">
        <Timer className="size-4 text-gold" />
        <span className="text-sm font-semibold">Time logger</span>
      </div>
      <p className="mt-1 truncate text-[11px] text-muted-foreground">
        {active
          ? `Clocked in · ${active.target_label ?? active.area}`
          : "Choose an object of work"}
      </p>
      <div className="mt-3 flex gap-2">
        <label
          className="sr-only"
          htmlFor={`activity-target-${compact ? "sidebar" : "hero"}`}
        >
          Work target
        </label>
        <select
          id={`activity-target-${compact ? "sidebar" : "hero"}`}
          value={selection}
          onChange={(event) => setSelection(event.target.value)}
          disabled={Boolean(active)}
          className="min-w-0 flex-1 rounded-lg border border-border bg-background px-2 py-2 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-gold"
        >
          <optgroup label="Areas">
            {AREAS.map((area) => (
              <option key={area} value={`area:${area}`}>
                {area}
              </option>
            ))}
          </optgroup>
          {matters.length > 0 && (
            <optgroup label="My matters">
              {matters.map((matter) => (
                <option key={matter.id} value={`matter:${matter.id}`}>
                  {matter.matter_ref}
                </option>
              ))}
            </optgroup>
          )}
        </select>
        <button
          type="button"
          disabled={busy || sessions.isPending || (!active && !selection)}
          onClick={() => (active ? clockOut.mutate() : start())}
          className={`rounded-lg px-3 py-2 text-xs font-semibold transition-all duration-200 disabled:opacity-60 ${active ? "bg-destructive/15 text-destructive hover:bg-destructive/25" : "bg-gold text-background hover:bg-gold/90"}`}
        >
          {busy ? (
            <Loader2 className="size-3.5 animate-spin" />
          ) : active ? (
            "Clock-out"
          ) : (
            "Clock-in"
          )}
        </button>
      </div>
      {(clockIn.isError || clockOut.isError || sessions.isError) && (
        <p role="alert" className="mt-2 text-[10px] text-destructive">
          Could not update the time session. Please retry.
        </p>
      )}
      <details className="mt-3 border-t border-border pt-2">
        <summary className="cursor-pointer text-[11px] font-medium text-gold transition-all duration-200 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold">
          Time history by matter or area
        </summary>
        {sessions.isPending ? (
          <div className="mt-3 h-8 animate-pulse rounded bg-muted/60" />
        ) : groups.length ? (
          <ul className="mt-2 divide-y divide-border">
            {groups.map((group: ActivitySessionGroup) => (
              <li
                key={`${group.target_type}:${group.target_ref}`}
                className="flex items-center justify-between gap-2 py-2 text-xs"
              >
                <span className="min-w-0 truncate">
                  {group.target_label}
                  <span className="ml-2 text-muted-foreground">
                    {" · "}
                    {group.session_count}{" "}
                    {group.session_count === 1 ? "session" : "sessions"}
                  </span>
                </span>
                <span className="shrink-0 font-mono text-gold">
                  {fmt(group.total_duration)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-xs text-muted-foreground">
            No sessions recorded yet.
          </p>
        )}
      </details>
    </div>
  );
}

function InboxView({
  analyses,
  deadlines,
  matters,
}: {
  analyses: Array<{
    analysis_id: string;
    prompt_pack: string;
    status: string;
    created_at: string;
  }>;
  deadlines: DeadlineEvent[];
  matters: HomeMatter[];
}) {
  return (
    <div className="space-y-6">
      <section>
        <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          <Briefcase className="size-4 text-gold" /> Assignments and recent work
        </h4>
        {analyses.length || deadlines.length || matters.length ? (
          <ul className="divide-y divide-border">
            {analyses.slice(0, 5).map((item) => (
              <li
                key={item.analysis_id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">
                    {item.prompt_pack.replaceAll("_", " ")}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {item.status.replaceAll("_", " ")} ·{" "}
                    {new Date(item.created_at).toLocaleDateString("en-GB")}
                  </span>
                </span>
                <span className="rounded-full bg-gold/10 px-2 py-1 text-[10px] text-gold">
                  Analysis
                </span>
              </li>
            ))}
            {deadlines.slice(0, 3).map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">
                    {item.description}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Due {item.due_date}
                  </span>
                </span>
                <span className="rounded-full bg-warning/10 px-2 py-1 text-[10px] text-warning">
                  Deadline
                </span>
              </li>
            ))}
            {matters.slice(0, 3).map((matter) => (
              <li
                key={matter.id}
                className="flex items-center justify-between gap-3 py-3"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">
                    {matter.matter_ref}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {matter.status}
                  </span>
                </span>
                <Link
                  to="/workbench"
                  onClick={() => {
                    sessionStorage.setItem(
                      "redcase:workbench-matter",
                      matter.id,
                    );
                  }}
                  className="rounded-lg border border-border px-3 py-1.5 text-xs transition-all duration-200 hover:border-gold/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
                >
                  Open matter
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={CheckCircle2}
            title="Inbox is clear"
            description="New assignments and work product will appear here."
          />
        )}
      </section>
    </div>
  );
}

function TodayView({
  items,
}: {
  items: Array<{ id: string; title: string; kind: string; when: string }>;
}) {
  return items.length ? (
    <ul className="divide-y divide-border">
      {items.map((item) => (
        <li key={item.id} className="flex items-center gap-3 py-4">
          <span className="flex size-9 items-center justify-center rounded-lg bg-gold/10 text-gold">
            <CalendarClock className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">
              {item.title}
            </span>
            <span className="text-xs text-muted-foreground">
              {item.kind.replaceAll("_", " ")} ·{" "}
              {new Date(item.when).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          </span>
        </li>
      ))}
    </ul>
  ) : (
    <EmptyState
      icon={CalendarClock}
      title="Nothing scheduled today"
      description="Hearings, filings, reviews and meetings due today will be listed here."
    />
  );
}

function DeadlinesView({ events }: { events: DeadlineEvent[] }) {
  const [reminders, setReminders] = useState<string[]>([]);
  useEffect(() => {
    try {
      setReminders(
        JSON.parse(
          localStorage.getItem("redcase:deadline-reminders") ?? "[]",
        ) as string[],
      );
    } catch {
      setReminders([]);
    }
  }, []);
  const addReminder = (id: string) => {
    const next = [...new Set([...reminders, id])];
    setReminders(next);
    try {
      localStorage.setItem("redcase:deadline-reminders", JSON.stringify(next));
    } catch {
      /* Browser storage may be unavailable. */
    }
  };
  return events.length ? (
    <ul className="divide-y divide-border">
      {events.map((event) => (
        <li key={event.id} className="flex flex-wrap items-center gap-3 py-4">
          <span className="flex size-9 items-center justify-center rounded-lg bg-gold/10 text-gold">
            <FileClock className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium">
              {event.description}
            </span>
            <span className="text-xs text-muted-foreground">
              {event.event_type.replaceAll("_", " ")} · Due {event.due_date} ·
              Matter {event.matter_id.slice(0, 8)}
            </span>
          </span>
          <button
            type="button"
            disabled={reminders.includes(event.id)}
            onClick={() => addReminder(event.id)}
            className="rounded-lg border border-border px-3 py-2 text-xs transition-all duration-200 hover:border-gold/60 disabled:cursor-default disabled:text-muted-foreground"
          >
            {reminders.includes(event.id) ? "Reminder set" : "Set reminder"}
          </button>
        </li>
      ))}
    </ul>
  ) : (
    <EmptyState
      icon={Clock3}
      title="No upcoming dates"
      description="Upcoming statutory deadlines and limitations will appear here."
    />
  );
}

function MattersView({
  matters,
  selectedMatterId,
  onSelectMatter,
  onBack,
}: {
  matters: HomeMatter[];
  selectedMatterId: string | null;
  onSelectMatter: (matterId: string) => void;
  onBack: () => void;
}) {
  const active = matters.filter(
    (matter) =>
      !["CLOSED", "COMPLETED", "ARCHIVED"].includes(
        matter.status.toUpperCase(),
      ),
  );
  const selectedMatter = active.find(
    (matter) => matter.id === selectedMatterId,
  );
  if (selectedMatter) {
    return (
      <article className="space-y-5">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1 text-xs font-medium text-gold transition-all duration-200 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
        >
          <ChevronRight className="size-3.5 rotate-180" /> Back to My matters
        </button>
        <div className="rounded-xl border border-border bg-surface p-5">
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-gold/10 text-gold">
              <Gavel className="size-5" />
            </span>
            <div className="min-w-0 flex-1">
              <h4 className="font-display text-lg font-semibold">
                {selectedMatter.matter_ref}
              </h4>
              <p className="mt-1 text-xs text-muted-foreground">
                Matter overview · {selectedMatter.status}
              </p>
            </div>
          </div>
          <p className="mt-5 text-sm leading-relaxed text-muted-foreground">
            {selectedMatter.progress_note ||
              "No progress update has been added."}
          </p>
          <Link
            to="/workbench"
            onClick={() =>
              sessionStorage.setItem(
                "redcase:workbench-matter",
                selectedMatter.id,
              )
            }
            className="mt-5 inline-flex items-center gap-2 rounded-lg bg-gold px-4 py-2.5 text-xs font-semibold text-background transition-all duration-200 hover:bg-gold/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
          >
            Open matter tools <ArrowUpRight className="size-3.5" />
          </Link>
        </div>
      </article>
    );
  }
  return active.length ? (
    <ul className="divide-y divide-border">
      {active.map((matter) => (
        <li key={matter.id} className="flex flex-wrap items-center gap-3 py-4">
          <span className="flex size-9 items-center justify-center rounded-lg bg-gold/10 text-gold">
            <Gavel className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium">
              {matter.matter_ref}
            </span>
            <span className="text-xs text-muted-foreground">
              {matter.status}
              {matter.progress_note ? ` · ${matter.progress_note}` : ""}
            </span>
          </span>
          <button
            type="button"
            onClick={() => onSelectMatter(matter.id)}
            className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-xs transition-all duration-200 hover:border-gold/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold"
          >
            View matter <ChevronRight className="size-3.5" />
          </button>
        </li>
      ))}
    </ul>
  ) : (
    <EmptyState
      icon={Scale}
      title="No active matters assigned"
      description="Matters assigned to you will appear here."
    />
  );
}

function EmptyState({
  icon: Icon,
  title,
  description,
}: {
  icon: typeof Scale;
  title: string;
  description: string;
}) {
  return (
    <div
      role="status"
      className="rounded-xl border border-dashed border-border px-5 py-12 text-center"
    >
      <Icon className="mx-auto size-7 text-muted-foreground" />
      <h4 className="mt-3 text-sm font-semibold">{title}</h4>
      <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
        {description}
      </p>
    </div>
  );
}

function LoadingRows() {
  return (
    <div aria-busy="true" aria-label="Loading workspace" className="space-y-3">
      {[0, 1, 2].map((item) => (
        <div key={item} className="h-14 animate-pulse rounded-lg bg-muted/60" />
      ))}
    </div>
  );
}
function ErrorState() {
  return (
    <div
      role="alert"
      className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
    >
      Could not load workspace information. Check your connection and try again.
    </div>
  );
}
