import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { CalendarClock, Calculator, AlertOctagon, Clock, CheckCircle2 } from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { DEADLINES, RULE_PRESETS, type Deadline } from "@/lib/aetoes-data";

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
        content: "Nigerian court-rule deadline computation and court diary for Aetoes Legal.",
      },
    ],
  }),
  component: Tracker,
});

const TODAY = new Date("2026-08-13T00:00:00Z");
const MONTH = 7; // August (0-indexed)
const YEAR = 2026;

const STATUS_STYLE: Record<Deadline["status"], { label: string; cls: string }> = {
  critical: { label: "Critical", cls: "bg-destructive/15 text-destructive" },
  due: { label: "Due soon", cls: "bg-warning/15 text-warning" },
  upcoming: { label: "Upcoming", cls: "bg-cyan/15 text-cyan" },
  filed: { label: "Filed", cls: "bg-success/15 text-success" },
};

function daysAway(iso: string) {
  return Math.round((new Date(iso + "T00:00:00Z").getTime() - TODAY.getTime()) / 86400000);
}

function Tracker() {
  const [service, setService] = useState("2026-08-13");
  const [preset, setPreset] = useState(RULE_PRESETS[0]!.label);

  const computed = useMemo(() => {
    const rule = RULE_PRESETS.find((r) => r.label === preset)!;
    const d = new Date(service + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + rule.days);
    // Nigerian rules: if the deadline falls on a weekend, it rolls to the next working day.
    let rolled = false;
    while (d.getUTCDay() === 0 || d.getUTCDay() === 6) {
      d.setUTCDate(d.getUTCDate() + 1);
      rolled = true;
    }
    return { date: d, days: rule.days, rolled };
  }, [service, preset]);

  const firstDay = new Date(Date.UTC(YEAR, MONTH, 1)).getUTCDay();
  const daysInMonth = new Date(Date.UTC(YEAR, MONTH + 1, 0)).getUTCDate();
  const cells = [
    ...Array.from({ length: firstDay }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  return (
    <AppShell eyebrow="Nigerian Court Rules Engine" title="Statutory Tracker">
      <div className="mx-auto max-w-6xl space-y-6">
        <div className="grid gap-4 sm:grid-cols-4">
          <Stat label="Critical this week" value="2" tone="text-destructive" />
          <Stat label="Due within 14 days" value="4" tone="text-warning" />
          <Stat label="Active matters" value="7" tone="text-cyan" />
          <Stat label="Filed on time (YTD)" value="100%" tone="text-success" />
        </div>

        <div className="grid gap-6 lg:grid-cols-[1.15fr_1fr]">
          {/* Calendar */}
          <section className="panel p-6">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <CalendarClock className="size-4 text-gold" /> August 2026 — Court Diary
            </h2>
            <div className="mt-5 grid grid-cols-7 gap-1 text-center font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
              {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
                <div key={i} className="pb-2">
                  {d}
                </div>
              ))}
              {cells.map((day, i) => {
                if (day === null) return <div key={`e${i}`} />;
                const iso = `2026-08-${String(day).padStart(2, "0")}`;
                const events = DEADLINES.filter((d) => d.date === iso);
                const isToday = iso === "2026-08-13";
                const top = events[0];
                return (
                  <div
                    key={iso}
                    className={`aspect-square rounded-md border p-1 text-left ${
                      isToday ? "border-gold bg-gold/10" : "border-border/60"
                    }`}
                  >
                    <div className={`text-[11px] ${isToday ? "text-gold" : "text-foreground/80"}`}>
                      {day}
                    </div>
                    {top && (
                      <div
                        className={`mt-1 truncate rounded px-1 py-0.5 text-[8px] leading-tight normal-case tracking-normal ${STATUS_STYLE[top.status].cls}`}
                      >
                        {top.task.split(" ").slice(0, 3).join(" ")}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            <div className="mt-5 flex flex-wrap gap-3 text-[11px] text-muted-foreground">
              {Object.entries(STATUS_STYLE).map(([k, v]) => (
                <span key={k} className={`rounded-full px-2 py-0.5 ${v.cls}`}>
                  {v.label}
                </span>
              ))}
            </div>
          </section>

          {/* Calculator */}
          <section className="panel p-6">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              <Calculator className="size-4 text-cyan" /> Deadline Calculator
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Computes from the trigger date under the applicable Nigerian court rule, rolling
              weekends to the next working day.
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
                {computed.days} days from trigger
                {computed.rolled ? " · rolled forward from a weekend" : ""} · reminder set for T-3.
              </div>
            </div>
          </section>
        </div>

        {/* List */}
        <section className="panel overflow-hidden">
          <div className="flex items-center gap-2 border-b border-border px-6 py-4">
            <Clock className="size-4 text-gold" />
            <h2 className="text-lg font-semibold">Upcoming Court Dates & Filings</h2>
          </div>
          <div className="divide-y divide-border">
            {DEADLINES.map((d) => {
              const away = daysAway(d.date);
              return (
                <div key={d.id} className="flex flex-wrap gap-4 px-6 py-4 hover:bg-surface-raised/60">
                  <div className="w-20 shrink-0">
                    <div className="font-mono text-xs text-muted-foreground">
                      {new Date(d.date + "T00:00:00Z").toLocaleDateString("en-GB", {
                        day: "2-digit",
                        month: "short",
                        timeZone: "UTC",
                      })}
                    </div>
                    <div
                      className={`text-[11px] ${away < 0 ? "text-success" : away <= 7 ? "text-destructive" : "text-muted-foreground"}`}
                    >
                      {away < 0 ? `${-away}d ago` : away === 0 ? "today" : `in ${away}d`}
                    </div>
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{d.task}</span>
                      <span
                        className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest ${STATUS_STYLE[d.status].cls}`}
                      >
                        {STATUS_STYLE[d.status].label}
                      </span>
                    </div>
                    <div className="text-sm text-muted-foreground">{d.matter}</div>
                    <div className="mt-1 font-mono text-[11px] text-gold">{d.rule}</div>
                    <div className="text-[11px] text-muted-foreground">
                      {d.court} · {d.computedFrom}
                    </div>
                  </div>
                  <div className="self-center">
                    {d.status === "filed" ? (
                      <CheckCircle2 className="size-5 text-success" />
                    ) : d.status === "critical" ? (
                      <AlertOctagon className="size-5 text-destructive" />
                    ) : (
                      <Clock className="size-5 text-muted-foreground" />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </AppShell>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="panel p-5">
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
        {label}
      </div>
      <div className={`mt-2 font-display text-3xl ${tone}`}>{value}</div>
    </div>
  );
}
