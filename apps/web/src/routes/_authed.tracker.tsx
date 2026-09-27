import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  AlertOctagon,
  CalendarClock,
  Calculator,
  CheckCircle2,
  Clock3,
  Gavel,
  ShieldAlert,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ApiError } from "@/lib/api/client";
import { useCourtDiaryEntries } from "@/lib/api/court-diary";
import { useDeadlineEvents } from "@/lib/api/deadlines";
import type { DeadlineEvent } from "@/lib/api/deadlines";

export const Route = createFileRoute("/_authed/tracker")({
  head: () => ({
    meta: [
      { title: "Tracker — RedCase" },
      {
        name: "description",
        content:
          "Computed obligations and scheduled court activities in one responsive workspace.",
      },
    ],
  }),
  component: Tracker,
});

type Urgency =
  "overdue" | "due-soon" | "pending" | "notified" | "dismissed" | "missed";
const URGENCY_STYLE: Record<Urgency, { label: string; cls: string }> = {
  overdue: { label: "Overdue", cls: "bg-destructive/15 text-destructive" },
  "due-soon": { label: "Due soon", cls: "bg-warning/15 text-warning" },
  pending: { label: "Pending", cls: "bg-steel/15 text-steel" },
  notified: { label: "Notified", cls: "bg-success/15 text-success" },
  dismissed: { label: "Dismissed", cls: "bg-muted text-muted-foreground" },
  missed: { label: "Missed", cls: "bg-destructive/15 text-destructive" },
};
const DAY_MS = 86_400_000;

function urgencyOf(event: DeadlineEvent, today: Date): Urgency {
  if (event.status === "MISSED") return "missed";
  if (event.status === "NOTIFIED") return "notified";
  if (event.status === "DISMISSED") return "dismissed";
  const due = new Date(`${event.due_date}T00:00:00Z`);
  const days = Math.round((due.getTime() - today.getTime()) / DAY_MS);
  return days < 0 ? "overdue" : days <= 7 ? "due-soon" : "pending";
}

function Tracker() {
  const [view, setView] = useState("deadlines");
  const [service, setService] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [preset, setPreset] = useState("FHC appearance — 14 calendar days");
  const deadlines = useDeadlineEvents();
  const diary = useCourtDiaryEntries();
  const today = useMemo(() => {
    const date = new Date();
    date.setHours(0, 0, 0, 0);
    return date;
  }, []);
  const obligations = useMemo(
    () =>
      [...(deadlines.data ?? [])]
        .filter(
          (event) =>
            event.event_type === "FILING_DEADLINE" ||
            event.event_type === "LIMITATION",
        )
        .sort((a, b) => a.due_date.localeCompare(b.due_date)),
    [deadlines.data],
  );
  const activities = useMemo(
    () =>
      [...(diary.data ?? [])].sort((a, b) =>
        a.starts_at.localeCompare(b.starts_at),
      ),
    [diary.data],
  );
  const urgencies = useMemo(
    () =>
      new Map(obligations.map((event) => [event.id, urgencyOf(event, today)])),
    [obligations, today],
  );
  const overdue = obligations.filter(
    (event) => urgencies.get(event.id) === "overdue",
  ).length;
  const dueSoon = obligations.filter(
    (event) => urgencies.get(event.id) === "due-soon",
  ).length;
  const active = obligations.filter(
    (event) => event.status === "PENDING" || event.status === "NOTIFIED",
  ).length;
  const presets = [
    {
      label: "FHC appearance — 14 calendar days",
      days: 14,
      source: "FHC Rules Order 9 Rule 1 (illustrative only)",
    },
    {
      label: "Lagos defence — 42 calendar days",
      days: 42,
      source: "Lagos HC Rules Order 15 Rule 1 (illustrative only)",
    },
    {
      label: "Court of Appeal notice — 90 calendar days",
      days: 90,
      source: "Court of Appeal Act section 24 (illustrative only)",
    },
  ];
  const rule = presets.find((item) => item.label === preset) ?? presets[0]!;
  const computedDate = new Date(`${service}T00:00:00Z`);
  computedDate.setUTCDate(computedDate.getUTCDate() + rule.days);

  return (
    <AppShell eyebrow="OBLIGATIONS · SCHEDULED ACTIVITIES" title="Tracker">
      <div className="mx-auto max-w-7xl space-y-5 pb-8">
        <Tabs value={view} onValueChange={setView}>
          <div className="flex flex-col gap-3 border-b border-border pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium">
                Keep legal obligations distinct from scheduled work.
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Deadlines are computed from triggering events. Court Diary
                records hearings, meetings and other activities.
              </p>
            </div>
            <TabsList
              aria-label="Tracker views"
              className="h-auto w-full justify-start sm:w-auto"
            >
              <TabsTrigger
                value="deadlines"
                className="flex-1 gap-2 px-4 py-2 sm:flex-none"
              >
                <Clock3 className="size-4" />
                Deadlines
                {view === "deadlines" && (
                  <span
                    className="size-1.5 rounded-full bg-gold"
                    aria-label="Active view"
                  />
                )}
              </TabsTrigger>
              <TabsTrigger
                value="diary"
                className="flex-1 gap-2 px-4 py-2 sm:flex-none"
              >
                <CalendarClock className="size-4" />
                Court Diary
                {view === "diary" && (
                  <span
                    className="size-1.5 rounded-full bg-gold"
                    aria-label="Active view"
                  />
                )}
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="deadlines" className="space-y-5">
            <section
              aria-label="Deadline summary"
              className="grid gap-3 sm:grid-cols-3"
            >
              <Stat
                label="Overdue obligations"
                value={deadlines.isPending ? "—" : String(overdue)}
                tone="text-destructive"
              />
              <Stat
                label="Due within 7 days"
                value={deadlines.isPending ? "—" : String(dueSoon)}
                tone="text-warning"
              />
              <Stat
                label="Active obligations"
                value={deadlines.isPending ? "—" : String(active)}
                tone="text-steel"
              />
            </section>

            <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(300px,0.8fr)]">
              <section className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
                <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-4 sm:px-5">
                  <div className="flex items-center gap-3">
                    <span className="flex size-9 items-center justify-center rounded-lg bg-gold/10 text-gold">
                      <Gavel className="size-4" />
                    </span>
                    <div>
                      <h2 className="text-sm font-semibold">
                        Computed obligations
                      </h2>
                      <p className="text-xs text-muted-foreground">
                        Filing and limitation dates · {obligations.length}{" "}
                        records
                      </p>
                    </div>
                  </div>
                  <span className="rounded-full bg-warning/10 px-2.5 py-1 text-[10px] font-medium text-warning">
                    Counsel validation required
                  </span>
                </header>
                {deadlines.isError ? (
                  <ErrorState error={deadlines.error} />
                ) : deadlines.isPending ? (
                  <SkeletonRows />
                ) : obligations.length === 0 ? (
                  <EmptyState
                    title="No computed obligations"
                    body="When a rule-backed filing or limitation obligation is recorded, it will appear here."
                  />
                ) : (
                  <div className="divide-y divide-border">
                    {obligations.map((event) => (
                      <DeadlineRow
                        key={event.id}
                        event={event}
                        urgency={urgencies.get(event.id)!}
                        today={today}
                      />
                    ))}
                  </div>
                )}
              </section>

              <section className="rounded-xl border border-border bg-surface p-4 shadow-sm sm:p-5">
                <div className="flex items-center gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-steel/10 text-steel">
                    <Calculator className="size-4" />
                  </span>
                  <div>
                    <h2 className="text-sm font-semibold">Date calculator</h2>
                    <p className="text-xs text-muted-foreground">
                      Preview only · not legal advice
                    </p>
                  </div>
                </div>
                <label className="mt-5 block">
                  <span className="text-xs font-medium">Trigger date</span>
                  <input
                    type="date"
                    value={service}
                    onChange={(event) => setService(event.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-gold"
                  />
                </label>
                <label className="mt-4 block">
                  <span className="text-xs font-medium">Illustrative rule</span>
                  <select
                    value={preset}
                    onChange={(event) => setPreset(event.target.value)}
                    className="mt-1.5 w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-gold"
                  >
                    {presets.map((item) => (
                      <option key={item.label}>{item.label}</option>
                    ))}
                  </select>
                </label>
                <div className="mt-4 rounded-lg bg-background p-4">
                  <p className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                    Indicative date
                  </p>
                  <p className="mt-2 font-display text-xl text-gold">
                    {computedDate.toLocaleDateString("en-GB", {
                      weekday: "long",
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                      timeZone: "UTC",
                    })}
                  </p>
                  <p className="mt-2 text-xs text-muted-foreground">
                    {rule.days} calendar days · {rule.source}
                  </p>
                </div>
                <p className="mt-3 flex items-start gap-2 rounded-lg border border-warning/30 bg-warning/5 p-3 text-xs leading-relaxed text-muted-foreground">
                  <ShieldAlert className="mt-0.5 size-4 shrink-0 text-warning" />
                  Unvalidated example only. Have counsel confirm the applicable
                  rule, trigger and computation before relying on any date.
                </p>
              </section>
            </div>
          </TabsContent>

          <TabsContent value="diary" className="space-y-5">
            <section className="grid gap-3 sm:grid-cols-3">
              <Stat
                label="Scheduled activities"
                value={
                  diary.isPending
                    ? "—"
                    : String(
                        activities.filter(
                          (entry) => entry.status === "SCHEDULED",
                        ).length,
                      )
                }
                tone="text-steel"
              />
              <Stat
                label="Hearings & mentions"
                value={
                  diary.isPending
                    ? "—"
                    : String(
                        activities.filter(
                          (entry) =>
                            entry.entry_type === "HEARING" ||
                            entry.entry_type === "MENTION",
                        ).length,
                      )
                }
                tone="text-gold"
              />
              <Stat
                label="All diary entries"
                value={diary.isPending ? "—" : String(activities.length)}
                tone="text-foreground"
              />
            </section>
            <section className="overflow-hidden rounded-xl border border-border bg-surface shadow-sm">
              <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-4 sm:px-5">
                <div className="flex items-center gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-steel/10 text-steel">
                    <CalendarClock className="size-4" />
                  </span>
                  <div>
                    <h2 className="text-sm font-semibold">
                      Scheduled activities
                    </h2>
                    <p className="text-xs text-muted-foreground">
                      Hearings, meetings and court events
                    </p>
                  </div>
                </div>
                <span className="rounded-full bg-steel/10 px-2.5 py-1 text-[10px] font-medium text-steel">
                  Calendar entries · not filing deadlines
                </span>
              </header>
              {diary.isError ? (
                <ErrorState error={diary.error} />
              ) : diary.isPending ? (
                <SkeletonRows />
              ) : activities.length === 0 ? (
                <EmptyState
                  title="Your court diary is clear"
                  body="Scheduled hearings, meetings and mentions will appear here when added to the diary."
                />
              ) : (
                <div className="grid gap-3 p-3 sm:p-4">
                  {activities.map((entry) => (
                    <article
                      key={entry.id}
                      className="grid gap-3 rounded-xl border border-border/80 bg-background p-4 transition-all duration-200 hover:border-steel/40 sm:grid-cols-[110px_minmax(0,1fr)_auto] sm:items-center"
                    >
                      <div className="flex items-center gap-2 sm:block">
                        <span className="font-mono text-sm font-semibold text-gold">
                          {new Date(entry.starts_at).toLocaleDateString(
                            "en-GB",
                            { day: "2-digit", month: "short", timeZone: "UTC" },
                          )}
                        </span>
                        <span className="text-xs text-muted-foreground sm:mt-1 sm:block">
                          {new Date(entry.starts_at).toLocaleTimeString(
                            "en-GB",
                            {
                              hour: "2-digit",
                              minute: "2-digit",
                              timeZone: "UTC",
                            },
                          )}
                        </span>
                      </div>
                      <div className="min-w-0">
                        <h3 className="text-sm font-medium">{entry.title}</h3>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {entry.entry_type} · Matter{" "}
                          {entry.matter_id.slice(0, 8)}
                          {entry.courtroom ? ` · ${entry.courtroom}` : ""}
                        </p>
                        {entry.judge && (
                          <p className="mt-1 text-xs text-muted-foreground">
                            Before {entry.judge}
                          </p>
                        )}
                      </div>
                      <span
                        className={`w-fit rounded-full px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider ${entry.status === "SCHEDULED" ? "bg-steel/10 text-steel" : "bg-muted text-muted-foreground"}`}
                      >
                        {entry.status}
                      </span>
                    </article>
                  ))}
                </div>
              )}
            </section>
          </TabsContent>
        </Tabs>
      </div>
    </AppShell>
  );
}

function DeadlineRow({
  event,
  urgency,
  today,
}: {
  event: DeadlineEvent;
  urgency: Urgency;
  today: Date;
}) {
  const days = Math.round(
    (new Date(`${event.due_date}T00:00:00Z`).getTime() - today.getTime()) /
      DAY_MS,
  );
  return (
    <article className="grid gap-3 px-4 py-4 transition-all duration-200 hover:bg-background/60 sm:grid-cols-[90px_minmax(0,1fr)_auto] sm:items-center sm:px-5">
      <div className="flex items-baseline gap-2 sm:block">
        <time
          dateTime={event.due_date}
          className="font-mono text-sm font-semibold"
        >
          {new Date(`${event.due_date}T00:00:00Z`).toLocaleDateString("en-GB", {
            day: "2-digit",
            month: "short",
            timeZone: "UTC",
          })}
        </time>
        <span
          className={`text-[11px] ${days < 0 ? "text-destructive" : days <= 7 ? "text-warning" : "text-muted-foreground"}`}
        >
          {days < 0
            ? `${-days}d overdue`
            : days === 0
              ? "Today"
              : `In ${days}d`}
        </span>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-medium">{event.description}</h3>
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${URGENCY_STYLE[urgency].cls}`}
          >
            {URGENCY_STYLE[urgency].label}
          </span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          Matter {event.matter_id.slice(0, 8)} ·{" "}
          {event.event_type.replaceAll("_", " ")}
          {event.trigger_date
            ? ` · Trigger ${new Date(`${event.trigger_date}T00:00:00Z`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" })}`
            : ""}
        </p>
        <p className="mt-1 text-[11px] text-warning">
          {event.rule_id === null || !event.validated_by
            ? "Rule validation not confirmed — counsel review required"
            : `Validated by ${event.validated_by}${event.validated_at ? ` on ${new Date(event.validated_at).toLocaleDateString("en-GB")}` : ""}`}
        </p>
      </div>
      <div className="hidden sm:block">
        {urgency === "overdue" || urgency === "missed" ? (
          <AlertOctagon className="size-4 text-destructive" />
        ) : urgency === "notified" ? (
          <CheckCircle2 className="size-4 text-success" />
        ) : (
          <Clock3 className="size-4 text-muted-foreground" />
        )}
      </div>
    </article>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-sm sm:p-5">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </p>
      <p className={`mt-2 font-display text-3xl ${tone}`}>{value}</p>
    </div>
  );
}

function SkeletonRows() {
  return (
    <div
      className="space-y-3 p-4"
      aria-busy="true"
      aria-label="Loading tracker entries"
    >
      {[0, 1, 2].map((item) => (
        <div key={item} className="h-20 animate-pulse rounded-lg bg-muted/60" />
      ))}
    </div>
  );
}
function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div role="status" className="px-5 py-14 text-center">
      <CalendarClock className="mx-auto size-7 text-muted-foreground" />
      <h3 className="mt-3 text-sm font-semibold">{title}</h3>
      <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
        {body}
      </p>
    </div>
  );
}
function ErrorState({ error }: { error: unknown }) {
  const message =
    error instanceof ApiError && error.isAuthError
      ? "Your session is missing or expired. Sign in again."
      : error instanceof Error
        ? error.message
        : "The service is unavailable. Check your connection and retry.";
  return (
    <div role="alert" className="p-5">
      <p className="flex items-center gap-2 text-sm font-medium text-destructive">
        <ShieldAlert className="size-4" />
        Could not load this view
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{message}</p>
    </div>
  );
}
