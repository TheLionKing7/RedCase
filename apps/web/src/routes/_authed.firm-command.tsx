import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo } from "react";
import {
  Flame,
  Scale,
  Loader2,
  ArrowUpRight,
  ShieldCheck,
  Users,
  Search,
  ShieldAlert,
  CalendarClock,
} from "lucide-react";
import { AppShell } from "@/components/AppShell";
import { getFirmAdmin } from "@/lib/auth/supabase";
import { useDeadlineEvents } from "@/lib/api/deadlines";
import { useAnalyses } from "@/lib/api/workbench";
import type { Analysis } from "@/lib/api/workbench";
import { useFirmOverview, useAdminLedger, useFirmSettings } from "@/lib/api/firmAdmin";

// Part 3 Slice 2 — Firm Command (renamed from the partner dashboard).
//
// §8.5 (audit H3): admin capability is an ORTHOGONAL, grantable flag
// (JWT `app_metadata.is_firm_admin`), NOT derived from clearance. This is the
// admin-only "run-the-firm" surface: seats, the admin-grant ledger, and the
// firm-wide compose. The backend enforces with `require_firm_admin` (403 for any
// non-admin); getFirmAdmin() here only (de)selects the route, never guards data.

export const Route = createFileRoute("/_authed/firm-command")({
  head: () => ({
    meta: [
      { title: "Firm Command — RedCase" },
      {
        name: "description",
        content: "Run-the-firm command center for admins — seats, admin ledger, deadlines and analyses.",
      },
    ],
  }),
  component: FirmCommand,
});

const ADMIN_TOOLS = [
  { to: "/search", label: "Vault Search", sub: "Dual-vault retrieval", icon: Search },
  { to: "/red-teamer", label: "Case Red-Teamer", sub: "Adversarial analysis", icon: ShieldAlert },
  { to: "/tracker", label: "Statutory Tracker", sub: "Deadline computation", icon: CalendarClock },
] as const;

function Stat({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="panel p-5">
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{label}</div>
      <div className={`mt-2 font-display text-3xl ${tone}`}>{value}</div>
    </div>
  );
}

function AnalysisStatus({ status }: { status: Analysis["status"] }) {
  const map: Record<string, { label: string; cls: string }> = {
    COMPLETE: { label: "Complete", cls: "bg-success/15 text-success" },
    RUNNING: { label: "Running", cls: "bg-steel/15 text-steel" },
    FAILED: { label: "Failed", cls: "bg-destructive/15 text-destructive" },
  };
  const s = map[status] ?? { label: "Needs review", cls: "bg-warning/15 text-warning" };
  return (
    <span className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest ${s.cls}`}>
      {s.label}
    </span>
  );
}

function FirmCommand() {
  const firmAdmin = getFirmAdmin();
  const overview = useFirmOverview();
  const ledger = useAdminLedger();
  const settings = useFirmSettings();
  const deadlines = useDeadlineEvents();
  const analyses = useAnalyses();

  const deadlineStats = useMemo(() => {
    const events = deadlines.data ?? [];
    const now = new Date();
    const todayIso = now.toISOString().slice(0, 10);
    const in14 = new Date(now.getTime() + 14 * 86400_000).toISOString().slice(0, 10);
    const overdue = events.filter(
      (e) => e.status !== "MISSED" && e.status !== "DISMISSED" && e.due_date < todayIso,
    ).length;
    const due14 = events.filter(
      (e) =>
        e.status !== "MISSED" &&
        e.status !== "DISMISSED" &&
        e.due_date >= todayIso &&
        e.due_date <= in14,
    ).length;
    const missed = events.filter((e) => e.status === "MISSED").length;
    return { overdue, due14, missed };
  }, [deadlines.data]);

  const upcoming = useMemo(() => {
    const events = deadlines.data ?? [];
    return [...events]
      .filter((e) => e.status !== "MISSED" && e.status !== "DISMISSED")
      .sort((a, b) => a.due_date.localeCompare(b.due_date))
      .slice(0, 6);
  }, [deadlines.data]);

  const recentAnalyses = useMemo(() => {
    const items = analyses.data ?? [];
    return [...items].sort((a, b) => a.created_at.localeCompare(b.created_at)).reverse().slice(0, 5);
  }, [analyses.data]);

  const seats = overview.data?.seats;
  const entries = ledger.data?.entries ?? [];

  return (
    <AppShell eyebrow="Firm Command Center" title="Firm Command">
      <div className="mx-auto max-w-7xl space-y-6">
        {!firmAdmin ? (
          <section className="panel glow-gold flex flex-col items-start gap-3 p-6">
            <ShieldCheck className="size-5 text-destructive" />
            <h2 className="text-lg font-semibold">Firm-admin capability required</h2>
            <p className="max-w-2xl text-sm text-muted-foreground">
              This run-the-firm surface is reserved for users carrying the{" "}
              <span className="font-mono text-xs">is_firm_admin</span> capability on their session. If you
              believe this is a mistake, ask the managing partner to grant it. (Admin capability is enforced
              server-side — this view is never a guard.)
            </p>
          </section>
        ) : (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Plan" value={seats?.plan ?? "—"} tone="text-gold" />
              <Stat
                label="Seats used"
                value={seats ? `${seats.current_seats}/${seats.max_seats}` : "—"}
                tone="text-steel"
              />
              <Stat label="Overdue deadlines" value={String(deadlineStats.overdue)} tone="text-destructive" />
              <Stat label="Due in 14 days" value={String(deadlineStats.due14)} tone="text-warning" />
            </div>

            {settings.data && (
              <section className="panel p-6">
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  <ArrowUpRight className="size-4 text-gold" /> Firm
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  {settings.data.firm.name} · slug{" "}
                  <span className="font-mono text-xs">{settings.data.firm.slug}</span> ·{" "}
                  {settings.data.firm.jurisdiction}
                </p>
              </section>
            )}

            <div className="grid gap-6 lg:grid-cols-2">
              <section className="panel p-6">
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  <Users className="size-4 text-gold" /> Admin capability ledger
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Append-only grant/revoke trail for the{" "}
                  <span className="font-mono text-xs">is_firm_admin</span> flag.
                </p>
                {ledger.isPending ? (
                  <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" /> Loading ledger&hellip;
                  </div>
                ) : entries.length === 0 ? (
                  <div className="mt-4 rounded-lg border border-border/60 p-4 text-sm text-muted-foreground">
                    No admin events recorded.
                  </div>
                ) : (
                  <ul className="mt-4 space-y-2">
                    {entries.slice(0, 8).map((e) => (
                      <li key={e.id} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-4 py-3">
                        <div>
                          <div className="font-mono text-xs">{e.user_ref}</div>
                          <div className="font-mono text-[10px] text-muted-foreground">by {e.granted_by}</div>
                        </div>
                        <span
                          className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest ${
                            e.action === "GRANTED"
                              ? "bg-success/15 text-success"
                              : "bg-destructive/15 text-destructive"
                          }`}
                        >
                          {e.action}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
              <section className="panel p-6">
                <h2 className="flex items-center gap-2 text-lg font-semibold">
                  <Flame className="size-4 text-gold" /> Upcoming deadlines
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Firm-wide statutory and court deadlines, soonest first.
                </p>
                {deadlines.isPending ? (
                  <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="size-4 animate-spin" /> Loading deadlines&hellip;
                  </div>
                ) : deadlines.isError || upcoming.length === 0 ? (
                  <div className="mt-4 rounded-lg border border-border/60 p-4 text-sm text-muted-foreground">
                    {deadlines.isError ? "Deadline service unavailable right now." : "No deadlines on the firm calendar yet."}
                  </div>
                ) : (
                  <ul className="mt-4 space-y-2">
                    {upcoming.map((e) => (
                      <li key={e.id} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-4 py-3">
                        <div>
                          <div className="text-sm font-medium">{e.description}</div>
                          <div className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                            {e.event_type.replaceAll("_", " ")}
                          </div>
                        </div>
                        <div className="text-right">
                          <div className="font-mono text-sm">
                            {new Date(e.due_date).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}
                          </div>
                          <div className="font-mono text-[10px] text-muted-foreground">due</div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>

            <section className="panel p-6">
              <h2 className="flex items-center gap-2 text-lg font-semibold">
                <Scale className="size-4 text-gold" /> Recent workbench analyses
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Latest adversarial briefs and reviews across the firm.
              </p>
              {analyses.isPending ? (
                <div className="mt-4 flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="size-4 animate-spin" /> Loading analyses&hellip;
                </div>
              ) : analyses.isError || recentAnalyses.length === 0 ? (
                <div className="mt-4 rounded-lg border border-border/60 p-4 text-sm text-muted-foreground">
                  {analyses.isError ? "Workbench service unavailable right now." : "No workbench analyses have been run yet."}
                </div>
              ) : (
                <ul className="mt-4 grid gap-3 sm:grid-cols-2">
                  {recentAnalyses.map((a) => (
                    <li key={a.analysis_id} className="flex items-center justify-between gap-3 rounded-lg border border-border/60 px-4 py-3">
                      <span className="text-sm font-medium">{a.prompt_pack.replaceAll("_", " ")}</span>
                      <AnalysisStatus status={a.status} />
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section>
              <h2 className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
                Jump to a tool
              </h2>
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {ADMIN_TOOLS.map(({ to, label, sub, icon: Icon }) => (
                  <Link
                    key={to}
                    to={to}
                    className="group flex items-start gap-3 rounded-xl border border-border/70 bg-background/60 p-4 transition-all duration-200 hover:border-gold/50 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-gold/40"
                  >
                    <Icon className="mt-0.5 size-4 shrink-0 text-steel transition-colors group-hover:text-gold" />
                    <span>
                      <span className="block text-sm font-medium">{label}</span>
                      <span className="mt-0.5 block text-[11px] text-muted-foreground">{sub}</span>
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}

