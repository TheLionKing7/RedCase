import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  CalendarClock,
  Calculator,
  AlertOctagon,
  Clock,
  CheckCircle2,
  ShieldAlert,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { ApiError } from "@/lib/api/client";
import { useDeadlineEvents } from "@/lib/api/deadlines";
import type { DeadlineEvent } from "@/lib/api/deadlines";

export const Route = createFileRoute("/tracker")({
  head: () => ({
    meta: [
      { title: "Statutory Tracker — Aetoes Ops Hub" },
      {
        name: "description",
        content:
          "Automatic filing-deadline computation under Nigerian Court Rules with a live calendar of upcoming court dates and alert statuses.",
      },
      { property: "og:title", content: "Statutory Tracker — Aetoes Ops Hub" },
      {
        property: "og:description",
        content:
          "Nigerian court-rule deadline computation and court diary for Aetoes Legal.",
      },
    ],
  }),
  component: Tracker,
});

// Display urgency derived from §3.1 status + due_date — no fields invented.
type Urgency =
  "overdue" | "due-soon" | "pending" | "notified" | "dismissed" | "missed";

const URGENCY_STYLE: Record<Urgency, { label: string; cls: string }> = {
  overdue: { label: "Overdue", cls: "bg-destructive/15 text-destructive" },
  "due-soon": { label: "Due soon", cls: "bg-warning/15 text-warning" },
  pending: { label: "Pending", cls: "bg-cyan/15 text-cyan" },
  notified: { label: "Notified", cls: "bg-success/15 text-success" },
  dismissed: { label: "Dismissed", cls: "bg-muted text-muted-foreground" },
  missed: { label: "Missed", cls: "bg-destructive/15 text-destructive" },
};

function urgencyOf(ev: DeadlineEvent, today: Date): Urgency {
  if (ev.status === "MISSED") return "missed";
  if (ev.status === "NOTIFIED") return "notified";
  if (ev.status === "DISMISSED") return "dismissed";
  const due = new Date(ev.due_date + "T00:00:00Z");
  const days = Math.round((due.getTime() - today.getTime()) / 86400000);
  if (days < 0) return "overdue";
  if (days <= 7) return "due-soon";
  return "pending";
}

const DAY_MS = 86400000;

/** Starter rule-pack presets for the local calculator. Per Phase3 §3.1 these
 *  ship UNVALIDATED — they move to the deadline_rules table and stay disabled
 *  until Nigerian counsel validates them. */
const RULE_PRESETS = [
  {
    label: "Memorandum of Appearance — FHC (14 days)",
    days: 14,
    source: "Order 9 Rule 1, FHC Rules 2019",
  },
  {
    label: "Statement of Defence — Lagos HC (42 days)",
    days: 42,
    source: "Order 15 Rule 1, Lagos HC Rules 2019",
  },
  {
    label: "Notice of Appeal, interlocutory — CA (14 days)",
    days: 14,
    source: "S.24(2)(a) Court of Appeal Act",
  },
  {
    label: "Notice of Appeal, final — CA (90 days)",
    days: 90,
    source: "S.24(2)(b) Court of Appeal Act",
  },
  {
    label: "Record of Appeal transmission — CA (60 days)",
    days: 60,
    source: "Order 8 Rule 1, CA Rules 2021",
  },
  {
    label: "Reply on points of law — Lagos HC (7 days)",
    days: 7,
    source: "Order 26 Rule 5, Lagos HC Rules 2019",
  },
];

function Tracker() {
  const [service, setService] = useState(() =>
    new Date().toISOString().slice(0, 10),
  );
  const [preset, setPreset] = useState(RULE_PRESETS[0]!.label);

  const eventsQuery = useDeadlineEvents();
  const events = useMemo(
    () =>
      [...(eventsQuery.data ?? [])].sort((a, b) =>
        a.due_date.localeCompare(b.due_date),
      ),
    [eventsQuery.data],
  );

  // Real "today" — the MVP's hardcoded 2026-08-13 is gone.
  const today = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  }, []);

  const computed = useMemo(() => {
    const rule = RULE_PRESETS.find((r) => r.label === preset)!;
    const d = new Date(service + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + rule.days);
    let rolled = false;
    while (d.getUTCDay() === 0 || d.getUTCDay() === 6) {
      d.setUTCDate(d.getUTCDate() + 1);
      rolled = true;
    }
    return { date: d, days: rule.days, rolled, source: rule.source };
  }, [service, preset]);

  const urgencies = useMemo(
    () => new Map(events.map((ev) => [ev.id, urgencyOf(ev, today)])),
    [events, today],
  );
  const overdue = events.filter(
    (ev) => urgencies.get(ev.id) === "overdue",
  ).length;
  const due14 = events.filter((ev) => {
    const u = urgencies.get(ev.id);
    if (u !== "due-soon" && u !== "overdue") return false;
    const days = Math.round(
      (new Date(ev.due_date + "T00:00:00Z").getTime() - today.getTime()) /
        DAY_MS,
    );
    return days <= 14;
  }).length;
  const active = events.filter(
    (ev) => ev.status === "PENDING" || ev.status === "NOTIFIED",
  ).length;
  const missed = events.filter((ev) => ev.status === "MISSED").length;

  // Calendar for the current real month, with events keyed by due_date.
  const calYear = today.getFullYear();
  const calMonth = today.getMonth();
  const firstDay = new Date(calYear, calMonth, 1).getDay();
  const daysInMonth = new Date(calYear, calMonth + 1, 0).getDate();
  const cells = [
    ...Array.from({ length: firstDay }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  const byDate = useMemo(() => {
    const m = new Map<string, DeadlineEvent>();
    for (const ev of events) {
      if (!m.has(ev.due_date)) m.set(ev.due_date, ev);
    }
    return m;
  }, [events]);
  const monthName = today.toLocaleDateString("en-GB", {
    month: "long",
    year: "numeric",
  });

  return (
    <AppShell eyebrow="Nigerian Court Rules Engine" title="Statutory Tracker">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="grid gap-4 sm:grid-cols-4">
          <Stat
            label="Overdue"
            value={String(overdue)}
            tone="text-destructive"
          />
          <Stat
            label="Due within 14 days"
            value={String(due14)}
            tone="text-warning"
          />
          <Stat label="Active events" value={String(active)} tone="text-cyan" />
          <Stat
            label="Missed"
            value={String(missed)}
            tone="text-muted-foreground"
          />
        </div>

        {eventsQuery.isError && (
          <section className="panel border-destructive/40 p-6">
            <h2 className="flex items-center gap-2 text-base font-semibold text-destructive">
              <ShieldAlert className="size-4" /> Tracker unavailable
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {eventsQuery.error instanceof ApiError &&
              eventsQuery.error.isAuthError
                ? "Your Supabase session is missing or expired. Sign in again."
                : eventsQuery.error instanceof Error
                  ? eventsQuery.error.message
                  : "The deadlines endpoint lands in Phase 3 (set VITE_API_DEV_ADAPTER=1 to preview with schema-shaped data)."}
            </p>
          </section>
        )}

        <div className="grid gap-6 lg:grid-cols-[1.15fr_1fr]">
          {/* Calendar */}
          <section className="panel p-6">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <CalendarClock className="size-4 text-gold" /> {monthName} — Court
              Diary
            </h2>
            <div className="mt-5 grid grid-cols-7 gap-1 text-center font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
                <div key={i} className="pb-2">
                  {d}
                </div>
              ))}
              {cells.map((day, i) => {
                if (day === null) return <div key={`e${i}`} />;
                const iso = `${calYear}-${String(calMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
                const ev = byDate.get(iso);
                const isToday = iso === today.toISOString().slice(0, 10);
                return (
                  <div
                    key={iso}
                    className={`aspect-square rounded-md border p-1 text-left ${
                      isToday ? "border-gold bg-gold/10" : "border-border/60"
                    }`}
                  >
                    <div
                      className={`text-[11px] ${isToday ? "text-gold" : "text-foreground/80"}`}
                    >
                      {day}
                    </div>
                    {ev && (
                      <div
                        className={`mt-1 truncate rounded px-1 py-0.5 text-[8px] leading-tight normal-case tracking-normal ${URGENCY_STYLE[urgencies.get(ev.id)!].cls}`}
                      >
                        {ev.description.split(" ").slice(0, 3).join(" ")}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="mt-5 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
              {Object.values(URGENCY_STYLE).map((v) => (
                <span
                  key={v.label}
                  className={`rounded-full px-2 py-0.5 ${v.cls}`}
                >
                  {v.label}
                </span>
              ))}
            </div>
          </section>

          {/* Calculator — local convenience; real computation is rule-pack
              driven server-side in Phase 3 (§3.1). */}
          <section className="panel p-6">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Calculator className="size-4 text-cyan" /> Deadline Calculator
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Computes from the trigger date under the applicable Nigerian court
              rule, rolling weekends to the next working day.
            </p>

            <label className="mt-5 block">
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                Trigger date (service / ruling)
              </span>
              <input
                type="date"
                value={service}
                onChange={(e) => setService(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-input bg-background/60 px-3 py-2.5 text-sm outline-none focus:border-gold"
              />
            </label>

            <label className="mt-4 block">
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                Applicable rule
              </span>
              <select
                value={preset}
                onChange={(e) => setPreset(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-input bg-background/60 px-3 py-2.5 text-sm outline-none focus:border-gold"
              >
                {RULE_PRESETS.map((r) => (
                  <option key={r.label} value={r.label} className="bg-surface">
                    {r.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="mt-5 rounded-lg bg-surface-raised p-5 glow-cyan">
              <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-cyan">
                Computed filing deadline
              </div>
              <div className="mt-2 font-display text-2xl text-gradient-gold">
                {computed.date.toLocaleDateString("en-GB", {
                  weekday: "long",
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                  timeZone: "UTC",
                })}
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                {computed.days} calendar days from trigger
                {computed.rolled
                  ? " · rolled forward from a weekend"
                  : ""} · {computed.source}
              </div>
              <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-warning/15 px-2 py-0.5 text-[10px] uppercase tracking-widest text-warning">
                ⚠ Unvalidated rule — counsel review pending (Phase3 §3.1)
              </div>
            </div>
          </section>
        </div>

        {/* List */}
        <section className="panel overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border px-6 py-4">
            <Clock className="size-4 text-gold" />
            <h2 className="text-lg font-semibold">
              Upcoming Court Dates & Filings
            </h2>
          </div>
          {eventsQuery.isPending ? (
            <div className="space-y-2 p-6">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-16 animate-pulse rounded bg-surface-raised/60"
                />
              ))}
            </div>
          ) : (
            <div className="divide-y divide-border">
              {events.map((d) => {
                const u = urgencies.get(d.id)!;
                const away = Math.round(
                  (new Date(d.due_date + "T00:00:00Z").getTime() -
                    today.getTime()) /
                    DAY_MS,
                );
                return (
                  <div
                    key={d.id}
                    className="flex flex-wrap gap-4 px-6 py-4 hover:bg-surface-raised/60"
                  >
                    <div className="w-20 shrink-0">
                      <div className="font-mono text-xs text-muted-foreground">
                        {new Date(d.due_date + "T00:00:00Z").toLocaleDateString(
                          "en-GB",
                          {
                            day: "2-digit",
                            month: "short",
                            timeZone: "UTC",
                          },
                        )}
                      </div>
                      <div
                        className={`text-[11px] ${
                          away < 0
                            ? "text-destructive"
                            : away <= 7
                              ? "text-warning"
                              : "text-muted-foreground"
                        }`}
                      >
                        {away < 0
                          ? `${-away}d ago`
                          : away === 0
                            ? "today"
                            : `in ${away}d`}
                      </div>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{d.description}</span>
                        <span
                          className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest ${URGENCY_STYLE[u].cls}`}
                        >
                          {URGENCY_STYLE[u].label}
                        </span>
                      </div>
                      <div className="font-mono text-[11px] text-muted-foreground">
                        Matter {d.matter_id.slice(0, 8)} ·{" "}
                        {d.event_type.replaceAll("_", " ")}
                      </div>
                      {d.rule_id === null && (
                        <div className="mt-1 inline-flex items-center gap-1.5 rounded-full bg-warning/15 px-2 py-0.5 text-[10px] uppercase tracking-widest text-warning">
                          ⚠ Unvalidated rule
                        </div>
                      )}
                      {d.trigger_date && (
                        <div className="mt-1 text-[11px] text-muted-foreground">
                          Trigger:{" "}
                          {new Date(
                            d.trigger_date + "T00:00:00Z",
                          ).toLocaleDateString("en-GB", {
                            day: "2-digit",
                            month: "short",
                            year: "numeric",
                            timeZone: "UTC",
                          })}
                          {d.confidence !== null &&
                            ` · confidence ${(d.confidence * 100).toFixed(0)}%`}
                        </div>
                      )}
                    </div>
                    <div className="self-center">
                      {u === "missed" ? (
                        <AlertOctagon className="size-5 text-destructive" />
                      ) : u === "overdue" ? (
                        <AlertOctagon className="size-5 text-destructive" />
                      ) : u === "notified" ? (
                        <CheckCircle2 className="size-5 text-success" />
                      ) : (
                        <Clock className="size-5 text-muted-foreground" />
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </AppShell>
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
    <div className="panel p-5">
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </div>
      <div className={`mt-2 font-display text-3xl ${tone}`}>{value}</div>
    </div>
  );
}
